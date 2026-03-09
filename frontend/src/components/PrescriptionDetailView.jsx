import { useContext, useState, useEffect, useRef } from "react";
import { getPrescribers, getPatientInsurance, getInsuranceCompanies, addPatientInsurance, updatePrescriptionPicture, updatePrescription } from "@/api";
import { AuthContext } from "@/context/AuthContext";
import Badge from "@/components/Badge";

const DAW_CODES = {
  0: "No product selection indicated (generic substitution allowed)",
  1: "Substitution not allowed by prescriber (brand medically necessary)",
  2: "Patient requested brand",
  3: "Pharmacist selected brand",
  4: "Generic not in stock",
  5: "Brand dispensed because generic not available",
  6: "Override due to state law",
  7: "Brand required by insurance",
  8: "Generic not available in marketplace",
  9: "Other",
};

function AddInsuranceModal({ patientId, companies, onClose, onAdded, token }) {
  const [form, setForm] = useState({
    insurance_company_id: "",
    member_id: "",
    group_number: "",
    is_primary: true,
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const handleChange = (e) => {
    const val = e.target.type === "checkbox" ? e.target.checked : e.target.value;
    setForm({ ...form, [e.target.name]: val });
  };

  const handleSubmit = async () => {
    if (!form.insurance_company_id || !form.member_id) {
      setError("Insurance company and Member ID are required.");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      const result = await addPatientInsurance(patientId, {
        insurance_company_id: parseInt(form.insurance_company_id),
        member_id: form.member_id,
        group_number: form.group_number || null,
        is_primary: form.is_primary,
      }, token);
      onAdded(result);
    } catch (e) {
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  };

  const selectedCompany = companies.find((c) => String(c.id) === String(form.insurance_company_id));

  return (
    <div style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.55)",
      display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000,
    }}>
      <div className="card vstack" style={{ maxWidth: "460px", width: "92%", gap: "1rem", padding: "1.5rem" }}>
        <h3 style={{ margin: 0 }}>Add Insurance Plan</h3>

        <label>
          <strong>Insurance Company</strong>
          <select
            name="insurance_company_id"
            value={form.insurance_company_id}
            onChange={handleChange}
            style={{ width: "100%", padding: "0.5rem", marginTop: "0.25rem" }}
          >
            <option value="">— Select company —</option>
            {companies.map((c) => (
              <option key={c.id} value={c.id}>
                {c.plan_name} ({c.plan_id})
              </option>
            ))}
          </select>
        </label>

        {selectedCompany && (
          <div style={{ fontSize: "0.82rem", color: "var(--text-light)", background: "var(--surface,#f4f4f4)", borderRadius: "4px", padding: "0.5rem 0.75rem" }}>
            BIN: <strong>{selectedCompany.bin_number ?? "—"}</strong>
            {" · "}PCN: <strong>{selectedCompany.pcn ?? "—"}</strong>
            {" · "}Phone: <strong>{selectedCompany.phone_number ?? "—"}</strong>
          </div>
        )}

        <label>
          <strong>Member ID</strong>
          <input
            type="text"
            name="member_id"
            value={form.member_id}
            onChange={handleChange}
            placeholder="e.g. BCBS-001-A8821"
            style={{ width: "100%", padding: "0.5rem", marginTop: "0.25rem" }}
          />
        </label>

        <label>
          <strong>Group Number{" "}
            <span style={{ fontWeight: 400, color: "var(--text-light)" }}>(optional)</span>
          </strong>
          <input
            type="text"
            name="group_number"
            value={form.group_number}
            onChange={handleChange}
            placeholder="e.g. GRP-10042"
            style={{ width: "100%", padding: "0.5rem", marginTop: "0.25rem" }}
          />
        </label>

        <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", cursor: "pointer" }}>
          <input
            type="checkbox"
            name="is_primary"
            checked={form.is_primary}
            onChange={handleChange}
          />
          <strong>Set as primary insurance</strong>
        </label>

        {error && <div style={{ color: "var(--danger)", fontSize: "0.9rem" }}>{error}</div>}

        <div style={{ display: "flex", gap: "0.75rem", justifyContent: "flex-end" }}>
          <button className="btn btn-secondary" onClick={onClose} disabled={submitting}>Cancel</button>
          <button className="btn btn-primary" onClick={handleSubmit} disabled={submitting}>
            {submitting ? "Saving…" : "Add Insurance"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function PrescriptionDetailView({ prescription, patientName, patientId, onBack }) {
  const { token } = useContext(AuthContext);
  const [prescribers, setPrescribers] = useState([]);
  const [patientInsurance, setPatientInsurance] = useState([]);
  const [allCompanies, setAllCompanies] = useState([]);
  const [showAddInsurance, setShowAddInsurance] = useState(false);
  const [pictureUrl, setPictureUrl] = useState(prescription.picture_url ?? null);
  const [uploadingPicture, setUploadingPicture] = useState(false);
  const fileInputRef = useRef(null);
  const [editingExpiration, setEditingExpiration] = useState(false);
  const [expirationDate, setExpirationDate] = useState(prescription.expiration_date ?? "");
  const [savingExpiration, setSavingExpiration] = useState(false);

  const pid = patientId ?? prescription.patient_id;

  useEffect(() => {
    getPrescribers(token).then((data) => setPrescribers(data.items ?? data)).catch(console.error);
    getInsuranceCompanies(token).then(setAllCompanies).catch(console.error);
    if (pid) {
      getPatientInsurance(pid, token).then(setPatientInsurance).catch(console.error);
    }
  }, [pid, token]);

  const lr = prescription.latest_refill;
  const prescriber = prescribers.find((p) => p.id === prescription.prescriber_id);

  // Build fill count map: sort refill_history by id asc, assign sequential fill numbers
  const sortedHistory = [...(prescription.refill_history ?? [])].sort((a, b) => a.id - b.id);
  const fillCountMap = Object.fromEntries(sortedHistory.map((h, i) => [h.id, i + 1]));
  const activeInsurance = patientInsurance.filter((i) => i.is_active);

  const handleInsuranceAdded = (newIns) => {
    setPatientInsurance((prev) => {
      const updated = newIns.is_primary
        ? prev.map((i) => ({ ...i, is_primary: false }))
        : [...prev];
      return [...updated, newIns];
    });
    setShowAddInsurance(false);
  };

  const handleSaveExpiration = async () => {
    setSavingExpiration(true);
    try {
      await updatePrescription(prescription.id, { expiration_date: expirationDate || null }, token);
      setEditingExpiration(false);
    } catch (err) {
      alert(`Failed to save expiration date: ${err.message}`);
    } finally {
      setSavingExpiration(false);
    }
  };

  const handlePictureUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setUploadingPicture(true);
    try {
      const result = await updatePrescriptionPicture(prescription.id, file, token);
      setPictureUrl(result.picture_url ?? null);
    } catch (err) {
      alert(`Failed to upload image: ${err.message}`);
    } finally {
      setUploadingPicture(false);
    }
  };

  return (
    <div className="vstack">
      {showAddInsurance && (
        <AddInsuranceModal
          patientId={pid}
          companies={allCompanies}
          onClose={() => setShowAddInsurance(false)}
          onAdded={handleInsuranceAdded}
          token={token}
        />
      )}

      <h2>Prescription Detail</h2>

      {/* Script Info */}
      <div className="card vstack" style={{ gap: "0.5rem" }}>
        <h3 style={{ margin: 0 }}>Script Info</h3>
        <div className="hstack" style={{ gap: "2rem", flexWrap: "wrap" }}>
          <div><strong>Rx #:</strong> {prescription.id}</div>
          <div><strong>Patient:</strong> {patientName}</div>
          <div>
            <strong>Drug:</strong> {prescription.drug.drug_name} ({prescription.drug.manufacturer})
            {prescription.drug.niosh && (
              <span style={{ color: "var(--danger)", marginLeft: "0.5rem" }}>⚠ NIOSH</span>
            )}
          </div>
          <div><strong>NDC:</strong> {prescription.drug.ndc ?? "—"}</div>
        </div>
        <div className="hstack" style={{ gap: "2rem", flexWrap: "wrap" }}>
          <div>
            <strong>Prescriber:</strong>{" "}
            {prescriber
              ? `Dr. ${prescriber.first_name} ${prescriber.last_name}${prescriber.specialty ? ` · ${prescriber.specialty}` : ""} (NPI: ${prescriber.npi})`
              : `ID ${prescription.prescriber_id}`}
          </div>
          <div><strong>DAW Code:</strong> {prescription.daw_code} — {DAW_CODES[prescription.daw_code] ?? "Unknown"}</div>
        </div>
        <div className="hstack" style={{ gap: "2rem", flexWrap: "wrap" }}>
          <div><strong>Date Received:</strong> {new Date(prescription.date_received).toLocaleDateString()}</div>
          <div><strong>Remaining Qty on Script:</strong> {prescription.remaining_quantity}</div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <strong>Script Expires:</strong>
            {editingExpiration ? (
              <>
                <input
                  type="date"
                  value={expirationDate}
                  onChange={(e) => setExpirationDate(e.target.value)}
                  style={{ padding: "2px 6px" }}
                />
                <button
                  className="btn btn-primary"
                  style={{ padding: "2px 10px", fontSize: "0.85rem" }}
                  onClick={handleSaveExpiration}
                  disabled={savingExpiration}
                >
                  {savingExpiration ? "Saving…" : "Save"}
                </button>
                <button
                  className="btn btn-secondary"
                  style={{ padding: "2px 10px", fontSize: "0.85rem" }}
                  onClick={() => { setEditingExpiration(false); setExpirationDate(prescription.expiration_date ?? ""); }}
                  disabled={savingExpiration}
                >
                  Cancel
                </button>
              </>
            ) : (
              <>
                <span>
                  {expirationDate ? new Date(expirationDate).toLocaleDateString() : <em style={{ color: "var(--text-light)" }}>Not set</em>}
                </span>
                <button
                  className="btn btn-secondary"
                  style={{ padding: "2px 10px", fontSize: "0.85rem" }}
                  onClick={() => setEditingExpiration(true)}
                >
                  {expirationDate ? "Edit" : "Set"}
                </button>
              </>
            )}
          </div>
        </div>
        {prescription.instructions && (
          <div><strong>Instructions:</strong> {prescription.instructions}</div>
        )}
      </div>

      {/* Prescription Image */}
      <div className="card vstack" style={{ gap: "0.75rem" }}>
        <div className="hstack" style={{ justifyContent: "space-between", alignItems: "center" }}>
          <h3 style={{ margin: 0 }}>Prescription Image</h3>
          <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
            {uploadingPicture && <span style={{ fontSize: "0.85rem", color: "var(--text-light)" }}>Uploading…</span>}
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              style={{ display: "none" }}
              onChange={handlePictureUpload}
            />
            <button
              className="btn btn-primary"
              style={{ padding: "4px 14px", fontSize: "0.85rem" }}
              onClick={() => fileInputRef.current?.click()}
              disabled={uploadingPicture}
            >
              {pictureUrl ? "Replace Image" : "+ Upload Image"}
            </button>
          </div>
        </div>
        {pictureUrl ? (
          <img
            src={pictureUrl}
            alt="Prescription"
            style={{ maxWidth: "100%", maxHeight: "400px", objectFit: "contain", borderRadius: "6px", border: "1px solid var(--border, #dee2e6)" }}
          />
        ) : (
          <div style={{
            display: "flex", alignItems: "center", justifyContent: "center",
            height: "160px", border: "2px dashed var(--border, #dee2e6)",
            borderRadius: "6px", color: "var(--text-light)", fontSize: "0.95rem"
          }}>
            No Image Available
          </div>
        )}
      </div>

      {/* Latest Refill */}
      <div className="card vstack" style={{ gap: "0.5rem" }}>
        <h3 style={{ margin: 0 }}>Latest Refill</h3>
        {lr ? (
          <>
            <div className="hstack" style={{ gap: "2rem", flexWrap: "wrap" }}>
              <div><strong>Fill #:</strong> {fillCountMap[lr.id] ?? "—"}</div>
              <div><strong>State:</strong> <Badge state={lr.state} /></div>
              <div><strong>Priority:</strong> {lr.priority ?? "—"}</div>
            </div>
            <div className="hstack" style={{ gap: "2rem", flexWrap: "wrap" }}>
              <div><strong>Quantity:</strong> {lr.quantity}</div>
              <div><strong>Days Supply:</strong> {lr.days_supply}</div>
              {lr.due_date && (
                <div><strong>Due Date:</strong> {new Date(lr.due_date).toLocaleDateString()}</div>
              )}
            </div>
            <div className="hstack" style={{ gap: "2rem", flexWrap: "wrap" }}>
              {lr.completed_date && (
                <div><strong>Filled Date:</strong> {new Date(lr.completed_date).toLocaleDateString()}</div>
              )}
              {lr.sold_date && (
                <div><strong>Sold Date:</strong> {new Date(lr.sold_date).toLocaleDateString()}</div>
              )}
              {lr.next_pickup && (
                <div><strong>Next Pickup:</strong> {new Date(lr.next_pickup).toLocaleDateString()}</div>
              )}
            </div>

            {/* Billing summary */}
            <div
              style={{
                background: "var(--surface,#f8f9fa)",
                border: "1px solid var(--border,#dee2e6)",
                borderRadius: "6px",
                padding: "0.6rem 1rem",
                marginTop: "0.25rem",
              }}
            >
              <div style={{ fontWeight: 600, fontSize: "0.85rem", marginBottom: "0.35rem", color: "var(--text-light)" }}>
                BILLING
              </div>
              <div className="hstack" style={{ gap: "2rem", flexWrap: "wrap" }}>
                {lr.total_cost != null && (
                  <div>
                    <span style={{ fontSize: "0.8rem", color: "var(--text-light)" }}>Cash Price</span>
                    <div style={{ fontWeight: 600, fontSize: "1rem", textDecoration: lr.copay_amount != null ? "line-through" : "none", color: lr.copay_amount != null ? "var(--text-light)" : "inherit" }}>
                      ${Number(lr.total_cost).toFixed(2)}
                    </div>
                  </div>
                )}
                {lr.copay_amount != null ? (
                  <>
                    <div>
                      <span style={{ fontSize: "0.8rem", color: "var(--text-light)" }}>Insurance Pays</span>
                      <div style={{ fontWeight: 600, fontSize: "1rem", color: "var(--success, #27ae60)" }}>
                        ${Number(lr.insurance_paid).toFixed(2)}
                      </div>
                    </div>
                    <div>
                      <span style={{ fontSize: "0.8rem", color: "var(--text-light)" }}>Patient Copay</span>
                      <div style={{ fontWeight: 700, fontSize: "1.2rem", color: "var(--primary)" }}>
                        ${Number(lr.copay_amount).toFixed(2)}
                      </div>
                    </div>
                  </>
                ) : (
                  <div style={{ color: "var(--text-light)", fontSize: "0.85rem", alignSelf: "center" }}>
                    Billed as cash — no insurance applied
                  </div>
                )}
              </div>
            </div>
          </>
        ) : (
          <div style={{ color: "var(--text-light)" }}>No refills on file.</div>
        )}
      </div>

      {/* Refill History */}
      <div className="card vstack" style={{ gap: "0.5rem" }}>
        <h3 style={{ margin: 0 }}>Refill History</h3>
        {prescription.refill_history && prescription.refill_history.length > 0 ? (
          <table className="table">
            <thead>
              <tr>
                <th>Refill #</th>
                <th>Qty</th>
                <th>Days Supply</th>
                <th>Filled</th>
                <th>Sold</th>
                <th>Cash Price</th>
                <th>Insurance Billed</th>
                <th>Ins. Paid</th>
                <th>Copay</th>
              </tr>
            </thead>
            <tbody>
              {prescription.refill_history.map((h) => (
                <tr key={h.id}>
                  <td><strong style={{ color: "var(--primary)" }}>{fillCountMap[h.id]}</strong></td>
                  <td>{h.quantity}</td>
                  <td>{h.days_supply}</td>
                  <td>{h.completed_date ? new Date(h.completed_date).toLocaleDateString() : "—"}</td>
                  <td>{h.sold_date ? new Date(h.sold_date).toLocaleDateString() : "—"}</td>
                  <td>${Number(h.total_cost).toFixed(2)}</td>
                  <td>{h.insurance?.insurance_company?.plan_name ?? "—"}</td>
                  <td>{h.insurance_paid != null ? "$" + Number(h.insurance_paid).toFixed(2) : "—"}</td>
                  <td>{h.copay_amount != null ? "$" + Number(h.copay_amount).toFixed(2) : "Cash"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div style={{ color: "var(--text-light)" }}>No refill history on file.</div>
        )}
      </div>

      {/* Insurance on File */}
      <div className="card vstack" style={{ gap: "0.75rem" }}>
        <div className="hstack" style={{ justifyContent: "space-between", alignItems: "center" }}>
          <h3 style={{ margin: 0 }}>Insurance on File</h3>
          <button
            className="btn btn-primary"
            style={{ padding: "4px 14px", fontSize: "0.85rem" }}
            onClick={() => setShowAddInsurance(true)}
          >
            + Add Insurance
          </button>
        </div>

        {activeInsurance.length === 0 ? (
          <div style={{ color: "var(--text-light)" }}>No insurance plans on file for this patient.</div>
        ) : (
          activeInsurance.map((ins) => (
            <div
              key={ins.id}
              style={{
                background: "var(--surface, #f8f9fa)",
                border: ins.is_primary ? "1px solid var(--primary)" : "1px solid var(--border, #dee2e6)",
                borderRadius: "6px",
                padding: "0.65rem 1rem",
              }}
            >
              <div className="hstack" style={{ justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "0.5rem" }}>
                <div>
                  <div style={{ fontWeight: 600, fontSize: "1rem" }}>
                    {ins.insurance_company.plan_name}
                    {ins.is_primary && (
                      <span style={{
                        marginLeft: "0.5rem",
                        background: "var(--primary)", color: "#fff",
                        fontSize: "0.72rem", padding: "1px 7px", borderRadius: "10px", verticalAlign: "middle",
                      }}>
                        Primary
                      </span>
                    )}
                  </div>
                  <div style={{ fontSize: "0.85rem", color: "var(--text-light)", marginTop: "0.1rem" }}>
                    Plan ID: {ins.insurance_company.plan_id}
                  </div>
                </div>
                <div style={{ fontSize: "0.85rem", textAlign: "right" }}>
                  <div>Member ID: <strong>{ins.member_id}</strong></div>
                  {ins.group_number && <div>Group: <strong>{ins.group_number}</strong></div>}
                </div>
              </div>
              <div style={{ display: "flex", gap: "1.5rem", flexWrap: "wrap", marginTop: "0.35rem", fontSize: "0.8rem", color: "var(--text-light)" }}>
                {ins.insurance_company.bin_number && <span>BIN: {ins.insurance_company.bin_number}</span>}
                {ins.insurance_company.pcn && <span>PCN: {ins.insurance_company.pcn}</span>}
                {ins.insurance_company.phone_number && <span>Phone: {ins.insurance_company.phone_number}</span>}
              </div>
            </div>
          ))
        )}
      </div>

      <div>
        <button className="btn btn-secondary" onClick={onBack}>
          Back
        </button>
      </div>
    </div>
  );
}
