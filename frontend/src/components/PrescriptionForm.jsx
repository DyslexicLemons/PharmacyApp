import { useState, useEffect, useRef } from "react";
import { getDrugs, getPrescribers, searchPatients, getPatient } from "@/api";
import NewPatientForm from "./NewPatientForm";

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

const API = import.meta.env.VITE_API_BASE || 'http://localhost:8000';

export default function PrescriptionForm({ onBack, patientId }) {
  const [step, setStep] = useState(1);
  const [drugs, setDrugs] = useState([]);
  const [prescribers, setPrescribers] = useState([]);
  const [conflict, setConflict] = useState(null);

  // Patient search state (used when no patientId prop)
  const [patientQuery, setPatientQuery] = useState("");
  const [patientSearchResults, setPatientSearchResults] = useState([]);
  const [patientSearchError, setPatientSearchError] = useState("");
  const [selectedPatient, setSelectedPatient] = useState(null);
  const [showNewPatientForm, setShowNewPatientForm] = useState(false);
  const [newPatientPrefill, setNewPatientPrefill] = useState({ last: "", first: "" });

  const [picture, setPicture] = useState(null);
  const fileInputRef = useRef(null);

  const defaultExpiration = (() => {
    const d = new Date();
    d.setFullYear(d.getFullYear() + 1);
    return d.toISOString().split("T")[0];
  })();

  const today = new Date().toISOString().split("T")[0];

  const [form, setForm] = useState({
    drug_id: "",
    prescriber_id: "",
    quantity: "",
    days_supply: "",
    total_refills: "1",
    daw_code: 0,
    priority: "normal",
    date_received: today,
    due_date: "",
    expiration_date: defaultExpiration,
    instructions: "",
  });

  useEffect(() => {
    getDrugs().then(setDrugs).catch(console.error);
    getPrescribers().then(setPrescribers).catch(console.error);
    if (patientId) {
      getPatient(patientId).then(setSelectedPatient).catch(console.error);
    }
  }, [patientId]);

  const handlePatientSearch = async (e) => {
    e.preventDefault();
    setPatientSearchError("");
    setPatientSearchResults([]);
    try {
      const results = await searchPatients(patientQuery);
      if (results.length === 0) {
        const [last = "", first = ""] = patientQuery.split(",").map((s) => s.trim());
        setNewPatientPrefill({ last, first });
        setPatientSearchError("no_match");
      } else if (results.length === 1) {
        setSelectedPatient(results[0]);
      } else {
        setPatientSearchResults(results);
      }
    } catch (e) {
      setPatientSearchError(e.message);
    }
  };

  const handlePictureSelect = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => setPicture(reader.result);
    reader.readAsDataURL(file);
  };

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    const parsed = name === "daw_code" ? parseInt(value, 10) : (type === "checkbox" ? checked : value);
    setForm({ ...form, [name]: parsed });
  };

  const checkConflict = async () => {
    if (!selectedPatient || !form.drug_id) {
      alert("Please select patient and drug first");
      return;
    }
    try {
      const res = await fetch(
        `${API}/refills/check_conflict?patient_id=${selectedPatient.id}&drug_id=${form.drug_id}`
      );
      if (!res.ok) throw new Error("Conflict check failed");
      const data = await res.json();
      setConflict(data);
      if (data.has_conflict) {
        const proceed = confirm(
          `${data.message}\n\nActive refills: ${data.active_refills.length}\nDo you want to continue anyway?`
        );
        if (!proceed) return;
      }
      setStep(2);
    } catch (e) {
      alert(e.message);
    }
  };

  const handleSubmit = async (initialState) => {
    try {
      const res = await fetch(`${API}/refills/create_manual`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          patient_id: selectedPatient.id,
          drug_id: parseInt(form.drug_id),
          prescriber_id: parseInt(form.prescriber_id),
          quantity: parseInt(form.quantity),
          days_supply: parseInt(form.days_supply),
          total_refills: parseInt(form.total_refills),
          daw_code: form.daw_code,
          priority: form.priority,
          initial_state: initialState,
          date_received: form.date_received || null,
          due_date: form.due_date || null,
          expiration_date: form.expiration_date || null,
          instructions: form.instructions,
          picture: picture || null,
        }),
      });

      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || "Failed to create prescription");
      }

      const result = await res.json();
      alert(`Prescription created successfully!\nRefill ID: ${result.refill_id}\nState: ${result.state}`);
      if (onBack) onBack();
    } catch (e) {
      alert(e.message);
    }
  };

  const selectedDrug = drugs.find(d => d.id === parseInt(form.drug_id));
  const selectedPrescriber = prescribers.find(p => p.id === parseInt(form.prescriber_id));

  const missingFields = [
    !form.prescriber_id && "Prescriber",
    !form.quantity && "Quantity",
    !form.days_supply && "Days Supply",
    !form.instructions.trim() && "Instructions",
  ].filter(Boolean);

  return (
    <div className="vstack">
      <h2>Create New Prescription</h2>
      <p style={{ color: "var(--text-light)", marginBottom: "1rem" }}>
        Manual prescriptions bypass QT triage. Choose how to proceed after entry.
      </p>

      {step === 1 && (
        <div className="vstack" style={{ gap: "1rem" }}>
          <h3>Step 1: Select Patient & Drug</h3>

          {/* Patient section */}
          <div className="card" style={{ padding: "1rem" }}>
            <strong>Patient</strong>

            {showNewPatientForm ? (
              <div style={{ marginTop: "0.5rem" }}>
                <NewPatientForm
                  prefillLast={newPatientPrefill.last}
                  prefillFirst={newPatientPrefill.first}
                  onBack={() => { setShowNewPatientForm(false); setPatientSearchError(""); }}
                  onCreated={(patient) => {
                    setSelectedPatient(patient);
                    setShowNewPatientForm(false);
                    setPatientSearchError("");
                    setPatientQuery("");
                  }}
                />
              </div>
            ) : selectedPatient ? (
              <div style={{ marginTop: "0.5rem" }}>
                <div style={{ padding: "0.5rem", background: "var(--bg-light)", borderRadius: "4px" }}>
                  <strong>{selectedPatient.last_name.toUpperCase()}, {selectedPatient.first_name.toUpperCase()}</strong>
                  <div style={{ fontSize: "0.9rem", color: "var(--text-light)" }}>
                    DOB: {selectedPatient.dob} | {selectedPatient.address}
                  </div>
                </div>
                {!patientId && (
                  <button
                    className="btn btn-secondary"
                    style={{ marginTop: "0.5rem" }}
                    onClick={() => { setSelectedPatient(null); setPatientSearchResults([]); setPatientQuery(""); }}
                  >
                    Change Patient
                  </button>
                )}
              </div>
            ) : (
              <div style={{ marginTop: "0.5rem" }}>
                <form onSubmit={handlePatientSearch} style={{ display: "flex", gap: "0.5rem" }}>
                  <input
                    autoFocus
                    className="input"
                    placeholder="Search: Last, First"
                    value={patientQuery}
                    onChange={(e) => setPatientQuery(e.target.value)}
                    style={{ flex: 1 }}
                  />
                  <button className="btn btn-primary" type="submit">Search</button>
                </form>

                {patientSearchError === "no_match" && (
                  <div style={{ marginTop: "0.75rem" }}>
                    <div style={{ color: "var(--text-light)", fontSize: "0.9rem", marginBottom: "0.5rem" }}>
                      No matches for <strong>"{patientQuery}"</strong>. Create a new patient?
                    </div>
                    <div style={{ display: "flex", gap: "0.5rem" }}>
                      <button
                        className="btn btn-primary"
                        onClick={() => setShowNewPatientForm(true)}
                      >
                        Yes, Create Patient
                      </button>
                      <button
                        className="btn btn-secondary"
                        onClick={() => { setPatientSearchError(""); setPatientQuery(""); }}
                      >
                        No
                      </button>
                    </div>
                  </div>
                )}

                {patientSearchError && patientSearchError !== "no_match" && (
                  <div style={{ color: "var(--danger)", marginTop: "0.5rem", fontSize: "0.9rem" }}>
                    {patientSearchError}
                  </div>
                )}

                {patientSearchResults.length > 1 && (
                  <div style={{ marginTop: "0.5rem" }}>
                    <div style={{ fontSize: "0.9rem", color: "var(--text-light)", marginBottom: "0.25rem" }}>
                      Multiple matches — select one:
                    </div>
                    {patientSearchResults.map(p => (
                      <button
                        key={p.id}
                        className="btn btn-secondary"
                        style={{ display: "block", width: "100%", textAlign: "left", marginBottom: "0.25rem" }}
                        onClick={() => { setSelectedPatient(p); setPatientSearchResults([]); }}
                      >
                        {p.last_name.toUpperCase()}, {p.first_name.toUpperCase()} — DOB: {p.dob}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Drug section */}
          <div className="card" style={{ padding: "1rem" }}>
            <label>
              <strong>Drug</strong>
              <select
                name="drug_id"
                value={form.drug_id}
                onChange={handleChange}
                style={{ width: "100%", padding: "0.5rem", marginTop: "0.25rem" }}
              >
                <option value="">-- Select Drug --</option>
                {drugs.map(d => (
                  <option key={d.id} value={d.id}>
                    {d.drug_name} ({d.manufacturer}) - ${Number(d.cost).toFixed(2)}
                    {d.niosh && " ⚠️ NIOSH"}
                  </option>
                ))}
              </select>
            </label>

            {selectedDrug && (
              <div style={{ marginTop: "0.5rem", padding: "0.5rem", background: "var(--bg-light)", borderRadius: "4px" }}>
                <strong>{selectedDrug.drug_name}</strong> ({selectedDrug.manufacturer})
                {selectedDrug.description && (
                  <div style={{ fontSize: "0.9rem", color: "var(--text-light)", marginTop: "0.25rem" }}>
                    {selectedDrug.description}
                  </div>
                )}
                <div style={{ fontSize: "0.9rem", marginTop: "0.25rem" }}>
                  Cost: ${Number(selectedDrug.cost).toFixed(2)} | Class: {selectedDrug.drug_class}
                  {selectedDrug.niosh && <span style={{ color: "var(--danger)", marginLeft: "0.5rem" }}>⚠️ NIOSH HAZARDOUS</span>}
                </div>
              </div>
            )}
          </div>

          {conflict && (
            <div className="card" style={{
              padding: "1rem",
              background: conflict.has_conflict ? "rgba(239, 71, 111, 0.1)" : "rgba(6, 214, 160, 0.1)",
              border: `2px solid ${conflict.has_conflict ? "var(--danger)" : "var(--success)"}`
            }}>
              <h4 style={{ marginTop: 0 }}>Conflict Check Result</h4>
              <p>{conflict.message}</p>
              {conflict.active_refills.length > 0 && (
                <div>
                  <strong>Active Refills:</strong>
                  <ul>
                    {conflict.active_refills.map(r => (
                      <li key={r.id}>
                        ID {r.id}: {r.state} - Due {r.due_date} (Qty: {r.quantity})
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          <button
            className="btn btn-primary"
            onClick={checkConflict}
            disabled={!selectedPatient || !form.drug_id}
          >
            Check for Conflicts & Continue →
          </button>
        </div>
      )}

      {step === 2 && (
        <div className="vstack" style={{ gap: "1rem" }}>
          <h3>Step 2: Prescription Details</h3>

          {selectedPatient && (
            <div style={{ padding: "0.5rem 1rem", background: "var(--bg-light)", borderRadius: "4px", fontSize: "0.9rem" }}>
              Patient: <strong>{selectedPatient.last_name.toUpperCase()}, {selectedPatient.first_name.toUpperCase()}</strong> | Drug: <strong>{selectedDrug?.drug_name}</strong>
            </div>
          )}

          <div className="card" style={{ padding: "1rem" }}>
            <label>
              <strong>Prescriber</strong>
              <select
                name="prescriber_id"
                value={form.prescriber_id}
                onChange={handleChange}
                style={{ width: "100%", padding: "0.5rem", marginTop: "0.25rem" }}
                required
              >
                <option value="">-- Select Prescriber --</option>
                {prescribers.map(p => (
                  <option key={p.id} value={p.id}>
                    Dr. {p.first_name} {p.last_name} (NPI: {p.npi})
                  </option>
                ))}
              </select>
            </label>

            {selectedPrescriber && (
              <div style={{ marginTop: "0.5rem", fontSize: "0.9rem", color: "var(--text-light)" }}>
                {selectedPrescriber.phone_number} | {selectedPrescriber.address}
              </div>
            )}
          </div>

          <div className="card" style={{ padding: "1rem", display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
            <label>
              <strong>Quantity</strong>
              <input
                type="number"
                name="quantity"
                value={form.quantity}
                onChange={handleChange}
                min="1"
                required
                style={{ width: "100%", padding: "0.5rem", marginTop: "0.25rem" }}
              />
            </label>

            <label>
              <strong>Days Supply</strong>
              <input
                type="number"
                name="days_supply"
                value={form.days_supply}
                onChange={handleChange}
                min="1"
                required
                style={{ width: "100%", padding: "0.5rem", marginTop: "0.25rem" }}
              />
            </label>

            <label>
              <strong>Total Refills</strong>
              <input
                type="number"
                name="total_refills"
                value={form.total_refills}
                onChange={handleChange}
                min="1"
                style={{ width: "100%", padding: "0.5rem", marginTop: "0.25rem" }}
              />
            </label>

            <label>
              <strong>Date Received</strong>
              <input
                type="date"
                name="date_received"
                value={form.date_received}
                onChange={handleChange}
                style={{ width: "100%", padding: "0.5rem", marginTop: "0.25rem" }}
              />
            </label>

            <label>
              <strong>Due Date (optional)</strong>
              <input
                type="date"
                name="due_date"
                value={form.due_date}
                onChange={handleChange}
                style={{ width: "100%", padding: "0.5rem", marginTop: "0.25rem" }}
              />
            </label>

            <label>
              <strong>Script Expiration Date</strong>
              <input
                type="date"
                name="expiration_date"
                value={form.expiration_date}
                onChange={handleChange}
                style={{ width: "100%", padding: "0.5rem", marginTop: "0.25rem" }}
              />
            </label>
          </div>

          <div className="card" style={{ padding: "1rem", display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
            <label>
              <strong>Priority</strong>
              <select
                name="priority"
                value={form.priority}
                onChange={handleChange}
                style={{ width: "100%", padding: "0.5rem", marginTop: "0.25rem" }}
              >
                <option value="normal">Normal</option>
                <option value="high">High</option>
                <option value="stat">Stat</option>
              </select>
            </label>

            <label>
              <strong>DAW Code</strong>
              <select
                name="daw_code"
                value={form.daw_code}
                onChange={handleChange}
                style={{ width: "100%", padding: "0.5rem", marginTop: "0.25rem" }}
              >
                {Object.entries(DAW_CODES).map(([code, desc]) => (
                  <option key={code} value={code}>{code} — {desc}</option>
                ))}
              </select>
            </label>
          </div>

          <div className="card" style={{ padding: "1rem" }}>
            <label>
              <strong>Instructions <span style={{ color: "var(--danger)" }}>*</span></strong>
              <textarea
                name="instructions"
                value={form.instructions}
                onChange={handleChange}
                required
                rows={3}
                placeholder="e.g. Take 1 tablet by mouth once daily with food"
                style={{ width: "100%", padding: "0.5rem", marginTop: "0.25rem", resize: "vertical" }}
              />
            </label>
          </div>

          <div className="card" style={{ padding: "1rem" }}>
            <div className="hstack" style={{ justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem" }}>
              <strong>Prescription Image <span style={{ fontWeight: 400, color: "var(--text-light)" }}>(optional)</span></strong>
              <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/*"
                  style={{ display: "none" }}
                  onChange={handlePictureSelect}
                />
                <button
                  type="button"
                  className="btn btn-primary"
                  style={{ padding: "4px 14px", fontSize: "0.85rem" }}
                  onClick={() => fileInputRef.current?.click()}
                >
                  {picture ? "Replace Image" : "+ Upload Image"}
                </button>
                {picture && (
                  <button
                    type="button"
                    className="btn btn-secondary"
                    style={{ padding: "4px 14px", fontSize: "0.85rem" }}
                    onClick={() => { setPicture(null); fileInputRef.current.value = ""; }}
                  >
                    Remove
                  </button>
                )}
              </div>
            </div>
            {picture ? (
              <img
                src={picture}
                alt="Prescription"
                style={{ maxWidth: "100%", maxHeight: "300px", objectFit: "contain", borderRadius: "6px", border: "1px solid var(--border, #dee2e6)" }}
              />
            ) : (
              <div style={{
                display: "flex", alignItems: "center", justifyContent: "center",
                height: "120px", border: "2px dashed var(--border, #dee2e6)",
                borderRadius: "6px", color: "var(--text-light)", fontSize: "0.95rem"
              }}>
                No Image Attached
              </div>
            )}
          </div>

          {missingFields.length > 0 && (
            <div style={{
              padding: "0.75rem 1rem",
              background: "rgba(239, 71, 111, 0.1)",
              border: "1px solid var(--danger)",
              borderRadius: "4px",
              fontSize: "0.9rem",
              color: "var(--danger)",
            }}>
              <strong>Required fields missing:</strong> {missingFields.join(", ")}
            </div>
          )}

          <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap", alignItems: "center" }}>
            <button className="btn btn-secondary" onClick={() => setStep(1)}>
              ← Back
            </button>
            <button
              className="btn btn-success"
              onClick={() => handleSubmit("QP")}
              disabled={!form.prescriber_id || !form.quantity || !form.days_supply || !form.instructions.trim()}
            >
              Fill Now
            </button>
            <button
              className="btn btn-warning"
              onClick={() => handleSubmit("HOLD")}
              disabled={!form.prescriber_id || !form.quantity || !form.days_supply || !form.instructions.trim()}
            >
              Put on Hold
            </button>
            <button
              className="btn btn-primary"
              onClick={() => handleSubmit("SCHEDULED")}
              disabled={!form.prescriber_id || !form.quantity || !form.days_supply || !form.instructions.trim()}
            >
              Schedule
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
