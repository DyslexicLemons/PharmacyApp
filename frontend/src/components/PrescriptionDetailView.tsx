import React, { useContext, useState, useEffect, useRef } from "react";
import { getPrescribers, getPatientInsurance, getInsuranceCompanies, addPatientInsurance, updatePrescriptionPicture, updatePrescription, inactivatePrescription, holdPrescription } from "@/api";
import { AuthContext } from "@/context/AuthContext";
import { useNotification } from "@/context/NotificationContext";
import Badge from "@/components/Badge";
import { usePrescriptionLock } from "@/hooks/usePrescriptionLock";
import type { Prescription } from "@/types";

const DAW_CODES: Record<number, string> = {
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

interface InsuranceCompanyDetail {
  id: number;
  plan_name: string;
  plan_id: string;
  bin_number?: string | null;
  pcn?: string | null;
  phone_number?: string | null;
}

interface PatientInsuranceItem {
  id: number;
  is_active: boolean;
  is_primary: boolean;
  member_id: string;
  group_number?: string | null;
  insurance_company: InsuranceCompanyDetail;
}

interface PrescriberDetail {
  id: number;
  first_name: string;
  last_name: string;
  npi: string;
  specialty?: string;
  phone_number?: string;
  address?: string;
}

interface RefillHistoryItem {
  id: number;
  quantity: number;
  days_supply: number;
  completed_date?: string | null;
  sold_date?: string | null;
  total_cost: number | string;
  insurance_paid?: number | null;
  copay_amount?: number | null;
  insurance?: { insurance_company?: { plan_name?: string } } | null;
  state?: string | null;
}

interface LatestRefill {
  id?: number | null;
  state: string;
  priority?: string | null;
  quantity: number;
  days_supply: number;
  due_date?: string | null;
  completed_date?: string | null;
  sold_date?: string | null;
  next_pickup?: string | null;
  total_cost?: number | null;
  copay_amount?: number | null;
  insurance_paid?: number | null;
  insurance?: { insurance_company?: { plan_name?: string } } | null;
}

interface PrescriptionDetail {
  id: number;
  date_received: string;
  expiration_date?: string | null;
  daw_code: number;
  remaining_quantity: number;
  instructions?: string | null;
  is_inactive?: boolean;
  is_expired?: boolean;
  picture_url?: string | null;
  patient_id?: number;
  prescriber_id?: number;
  drug: {
    drug_name: string;
    ndc?: string | null;
    manufacturer: string;
    niosh?: boolean;
  };
  latest_refill?: LatestRefill | null;
  refill_history?: RefillHistoryItem[];
}

interface AddInsuranceModalProps {
  patientId: number;
  companies: InsuranceCompanyDetail[];
  onClose: () => void;
  onAdded: (ins: PatientInsuranceItem) => void;
  token: string | null;
}

interface AddInsuranceForm {
  insurance_company_id: string;
  member_id: string;
  group_number: string;
  is_primary: boolean;
}

function AddInsuranceModal({ patientId, companies, onClose, onAdded, token }: AddInsuranceModalProps) {
  const [form, setForm] = useState<AddInsuranceForm>({
    insurance_company_id: "",
    member_id: "",
    group_number: "",
    is_primary: true,
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const target = e.target as HTMLInputElement;
    const val = target.type === "checkbox" ? target.checked : target.value;
    setForm({ ...form, [target.name]: val });
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
      }, token!);
      onAdded(result as unknown as PatientInsuranceItem);
    } catch (e) {
      setError((e as Error).message);
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

interface InactivateModalProps {
  prescriptionId: number;
  onClose: () => void;
  onInactivated: (updated: unknown) => void;
  token: string | null;
}

function InactivateModal({ prescriptionId, onClose, onInactivated, token }: InactivateModalProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async () => {
    if (!username || !password) {
      setError("Username and password are required.");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      const result = await inactivatePrescription(prescriptionId, username, password, token!);
      onInactivated(result);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)",
      display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000,
    }}>
      <div className="card vstack" style={{ maxWidth: "420px", width: "92%", gap: "1rem", padding: "1.5rem", border: "2px solid var(--danger)" }}>
        <h3 style={{ margin: 0, color: "var(--danger)" }}>Inactivate Prescription</h3>

        {!confirmed ? (
          <>
            <p style={{ margin: 0, fontSize: "0.95rem" }}>
              Are you sure you want to <strong>inactivate</strong> this prescription?
              This action cannot be undone and will prevent future fills.
            </p>
            {error && <div style={{ color: "var(--danger)", fontSize: "0.9rem" }}>{error}</div>}
            <div style={{ display: "flex", gap: "0.75rem", justifyContent: "flex-end" }}>
              <button className="btn btn-secondary" onClick={onClose}>Cancel</button>
              <button className="btn" style={{ background: "var(--danger)", color: "#fff" }} onClick={() => setConfirmed(true)}>
                Yes, Inactivate
              </button>
            </div>
          </>
        ) : (
          <>
            <p style={{ margin: 0, fontSize: "0.95rem" }}>
              Verify your credentials to confirm this action.
            </p>
            <label>
              <strong>Username</strong>
              <input
                type="text"
                value={username}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setUsername(e.target.value)}
                autoFocus
                style={{ width: "100%", padding: "0.5rem", marginTop: "0.25rem" }}
              />
            </label>
            <label>
              <strong>Password</strong>
              <input
                type="password"
                value={password}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setPassword(e.target.value)}
                onKeyDown={(e: React.KeyboardEvent<HTMLInputElement>) => e.key === "Enter" && handleSubmit()}
                style={{ width: "100%", padding: "0.5rem", marginTop: "0.25rem" }}
              />
            </label>
            {error && <div style={{ color: "var(--danger)", fontSize: "0.9rem" }}>{error}</div>}
            <div style={{ display: "flex", gap: "0.75rem", justifyContent: "flex-end" }}>
              <button className="btn btn-secondary" onClick={onClose} disabled={submitting}>Cancel</button>
              <button
                className="btn"
                style={{ background: "var(--danger)", color: "#fff" }}
                onClick={handleSubmit}
                disabled={submitting}
              >
                {submitting ? "Verifying…" : "Confirm Inactivation"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

interface HoldModalProps {
  onClose: () => void;
  onConfirm: () => void;
  submitting: boolean;
}

function HoldModal({ onClose, onConfirm, submitting }: HoldModalProps) {
  return (
    <div style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.55)",
      display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000,
    }}>
      <div className="card vstack" style={{ maxWidth: "420px", width: "92%", gap: "1rem", padding: "1.5rem", border: "2px solid var(--warning, #f39c12)" }}>
        <h3 style={{ margin: 0, color: "var(--warning, #f39c12)" }}>Place Prescription on Hold</h3>
        <p style={{ margin: 0, fontSize: "0.95rem" }}>
          This will move the active refill to <strong>HOLD</strong> status.
          The refill can be resumed from the workflow queue.
        </p>
        <div style={{ display: "flex", gap: "0.75rem", justifyContent: "flex-end" }}>
          <button className="btn btn-secondary" onClick={onClose} disabled={submitting}>Cancel</button>
          <button
            className="btn"
            style={{ background: "var(--warning, #f39c12)", color: "#fff", minWidth: "100px" }}
            onClick={onConfirm}
            disabled={submitting}
          >
            {submitting ? "Holding…" : "Confirm Hold"}
          </button>
        </div>
      </div>
    </div>
  );
}

interface PrescriptionDetailViewProps {
  prescription: Prescription;
  patientName: string;
  patientId?: number;
  onBack?: () => void;
  onFill?: () => void;
  onPrescriptionUpdated?: (updated: unknown) => void;
  keyCmd?: string | null;
  onKeyCmdHandled?: () => void;
}

export default function PrescriptionDetailView({ prescription: rawPrescription, patientName, patientId, onBack, onFill, onPrescriptionUpdated, keyCmd, onKeyCmdHandled }: PrescriptionDetailViewProps) {
  const prescription = rawPrescription as PrescriptionDetail;
  const { token } = useContext(AuthContext);
  const { addNotification } = useNotification();
  const { lockError, lockPending } = usePrescriptionLock(prescription.id);
  const [prescribers, setPrescribers] = useState<PrescriberDetail[]>([]);
  const [patientInsurance, setPatientInsurance] = useState<PatientInsuranceItem[]>([]);
  const [allCompanies, setAllCompanies] = useState<InsuranceCompanyDetail[]>([]);
  const [showAddInsurance, setShowAddInsurance] = useState(false);
  const [showInactivate, setShowInactivate] = useState(false);
  const [showHold, setShowHold] = useState(false);
  const [holdingRx, setHoldingRx] = useState(false);
  const [isInactive, setIsInactive] = useState(prescription.is_inactive ?? false);
  const isExpired = !isInactive && (prescription.is_expired ?? false);
  const [pictureUrl, setPictureUrl] = useState<string | null>(prescription.picture_url ?? null);
  const [uploadingPicture, setUploadingPicture] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [_editingExpiration, _setEditingExpiration] = useState(false);
  const [expirationDate, _setExpirationDate] = useState(prescription.expiration_date ?? "");
  const [_savingExpiration, _setSavingExpiration] = useState(false);

  const pid = patientId ?? prescription.patient_id;

  useEffect(() => {
    getPrescribers(token!).then((data: { items?: PrescriberDetail[] } | PrescriberDetail[]) => {
      const items = Array.isArray(data) ? data : (data.items ?? data as unknown as PrescriberDetail[]);
      setPrescribers(items);
    }).catch(console.error);
    getInsuranceCompanies(token!).then((data) => setAllCompanies(data as unknown as InsuranceCompanyDetail[])).catch(console.error);
    if (pid) {
      getPatientInsurance(pid, token!).then((data) => setPatientInsurance(data as unknown as PatientInsuranceItem[])).catch(console.error);
    }
  }, [pid, token]);

  useEffect(() => {
    if (!keyCmd) return;
    const holdableStates = new Set(["QT", "QV1", "QP", "QV2", "SCHEDULED"]);
    const lr = prescription.latest_refill;
    if (keyCmd === "hold" && !isInactive && !isExpired && lr && holdableStates.has(lr.state)) {
      setShowHold(true);
    } else if (keyCmd === "inactivate" && !isInactive && !isExpired) {
      setShowInactivate(true);
    } else if (keyCmd === "fill") {
      const blockingFillStates = new Set(["QT", "QV1", "QP", "QV2", "READY"]);
      if (!isInactive && !isExpired && onFill && prescription.remaining_quantity > 0 && (!lr || !blockingFillStates.has(lr.state))) {
        onFill();
      }
    }
    onKeyCmdHandled?.();
  }, [keyCmd]);

  const handleInactivated = (updated: unknown) => {
    setIsInactive(true);
    setShowInactivate(false);
    addNotification("Prescription has been inactivated.", "success");
    onPrescriptionUpdated?.(updated);
    onBack?.();
  };

  const handleHold = async () => {
    setHoldingRx(true);
    try {
      const updated = await holdPrescription(prescription.id, token!);
      setShowHold(false);
      addNotification("Refill has been placed on hold.", "success");
      onPrescriptionUpdated?.(updated);
      onBack?.();
    } catch (err) {
      addNotification(`Failed to hold prescription: ${(err as Error).message}`, "error");
    } finally {
      setHoldingRx(false);
    }
  };

  const HOLDABLE_STATES = new Set(["QT", "QV1", "QP", "QV2", "SCHEDULED"]);
  const BLOCKING_FILL_STATES = new Set(["QT", "QV1", "QP", "QV2", "READY"]);

  const lr = prescription.latest_refill;
  const hasRemainingQty = prescription.remaining_quantity > 0;
  const canFill = !isInactive && !isExpired && onFill && hasRemainingQty && (!lr || !BLOCKING_FILL_STATES.has(lr.state));
  const prescriber = prescribers.find((p) => p.id === prescription.prescriber_id);

  // Build fill count across all refills (history + active)
  const allRefillIds: number[] = [...(prescription.refill_history ?? []).map((h) => h.id)];
  if (lr?.id != null && !allRefillIds.includes(lr.id)) allRefillIds.push(lr.id);
  allRefillIds.sort((a, b) => a - b);
  const fillCountMap = Object.fromEntries(allRefillIds.map((id, i) => [id, i + 1]));
  const activeInsurance = patientInsurance.filter((i) => i.is_active);

  const handleInsuranceAdded = (newIns: PatientInsuranceItem) => {
    setPatientInsurance((prev) => {
      const updated = newIns.is_primary
        ? prev.map((i) => ({ ...i, is_primary: false }))
        : [...prev];
      return [...updated, newIns];
    });
    setShowAddInsurance(false);
  };

  const _handleSaveExpiration = async () => {
    if (expirationDate) {
      const dateReceived = new Date(prescription.date_received);
      const selected = new Date(expirationDate);
      const maxExpiration = new Date(prescription.date_received);
      maxExpiration.setFullYear(maxExpiration.getFullYear() + 1);
      if (selected < dateReceived) {
        addNotification("Expiration date cannot be before the date received.", "warning");
        return;
      }
      if (selected > maxExpiration) {
        addNotification("Expiration date cannot be more than 1 year after the date received.", "warning");
        return;
      }
    }
    _setSavingExpiration(true);
    try {
      await updatePrescription(prescription.id, { expiration_date: expirationDate || null }, token!);
      _setEditingExpiration(false);
    } catch (err) {
      addNotification(`Failed to save expiration date: ${(err as Error).message}`, "error");
    } finally {
      _setSavingExpiration(false);
    }
  };

  const handlePictureUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadingPicture(true);
    try {
      const result = await updatePrescriptionPicture(prescription.id, file, token!);
      setPictureUrl((result as { picture_url?: string | null }).picture_url ?? null);
    } catch (err) {
      addNotification(`Failed to upload image: ${(err as Error).message}`, "error");
    } finally {
      setUploadingPicture(false);
    }
  };

  if (lockPending) {
    return null;
  }

  if (lockError) {
    return (
      <div className="vstack" style={{ alignItems: "center", justifyContent: "center", padding: "3rem", gap: "1rem" }}>
        <span style={{ fontSize: "2rem" }}>🔒</span>
        <p style={{ fontWeight: 600, textAlign: "center", margin: 0 }}>
          Rx #{prescription.id} — {prescription.drug?.drug_name}
        </p>
        <p style={{ textAlign: "center", margin: 0 }}>{lockError}</p>
        <button className="btn" onClick={onBack}>Go Back</button>
      </div>
    );
  }

  return (
    <div className="vstack">
      {showAddInsurance && pid != null && (
        <AddInsuranceModal
          patientId={pid}
          companies={allCompanies}
          onClose={() => setShowAddInsurance(false)}
          onAdded={handleInsuranceAdded}
          token={token}
        />
      )}

      {showInactivate && (
        <InactivateModal
          prescriptionId={prescription.id}
          onClose={() => setShowInactivate(false)}
          onInactivated={handleInactivated}
          token={token}
        />
      )}

      {showHold && (
        <HoldModal
          onClose={() => setShowHold(false)}
          onConfirm={handleHold}
          submitting={holdingRx}
        />
      )}

      <h2 style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
        <span>Rx #: {prescription.id}</span>
        <span style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
          {isInactive && <Badge state="INACTIVATED" />}
          {isExpired && <Badge state="EXPIRED" />}
          {lr && !isInactive && !isExpired && <span style={{ fontSize: "1.6rem" }}><Badge state={lr.state} /></span>}
        </span>
      </h2>

      {/* Main Info Card */}
      <div className="card" style={{ padding: "1.5rem", marginBottom: "1rem" }}>

        {/* Patient */}
        <div style={{ marginBottom: "0.75rem", paddingBottom: "0.6rem", borderBottom: "2px solid var(--bg-light)", display: "flex", gap: "2rem", alignItems: "baseline", flexWrap: "wrap" }}>
          <h3 style={{ margin: 0, fontSize: "1rem", flexShrink: 0 }}>Patient</h3>
          <span><strong>{patientName}</strong></span>
        </div>

        {/* Prescription + Prescriber + Image */}
        <div style={{ marginBottom: "1.25rem", paddingBottom: "1rem", borderBottom: "2px solid var(--bg-light)" }}>
          <h3 style={{ margin: "0 0 0.75rem 0", fontSize: "1.1rem" }}>Prescription</h3>
          <div style={{ display: "flex", gap: "1.5rem", alignItems: "flex-start" }}>

            {/* Left: prescription fields */}
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: "0.4rem 1.5rem", fontSize: "0.95rem" }}>
                <strong>Rx #:</strong>
                <span>{prescription.id}</span>

                <strong>Date Received:</strong>
                <span>{new Date(prescription.date_received).toLocaleDateString()}</span>

                <strong>Expiration:</strong>
                <span>
                  {expirationDate ? new Date(expirationDate).toLocaleDateString() : <em style={{ color: "var(--text-light)" }}>Not set</em>}
                </span>

                <strong>DAW Code:</strong>
                <span>{prescription.daw_code} — {DAW_CODES[prescription.daw_code] ?? "Unknown"}</span>

                <strong>Remaining Qty:</strong>
                <span>{prescription.remaining_quantity}</span>
              </div>

              {prescription.instructions && (
                <div style={{ marginTop: "0.75rem", padding: "0.5rem 0.75rem", background: "var(--bg-light)", borderRadius: "6px", fontSize: "0.9rem" }}>
                  <strong>Instructions:</strong>
                  <div style={{ marginTop: "0.25rem" }}>{prescription.instructions}</div>
                </div>
              )}
            </div>

            {/* Middle: prescriber */}
            {prescriber && (
              <div style={{ flexShrink: 0, width: "200px" }}>
                <div style={{ fontSize: "0.85rem", fontWeight: 600, color: "var(--text-light)", marginBottom: "0.4rem", textTransform: "uppercase", letterSpacing: "0.04em" }}>Prescriber</div>
                <div style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: "0.4rem 0.75rem", fontSize: "0.9rem" }}>
                  <strong>Name:</strong>
                  <span>Dr. {prescriber.first_name} {prescriber.last_name}</span>

                  <strong>NPI:</strong>
                  <span>{prescriber.npi}</span>

                  {prescriber.specialty && (
                    <>
                      <strong>Specialty:</strong>
                      <span>{prescriber.specialty}</span>
                    </>
                  )}

                  {prescriber.phone_number && (
                    <>
                      <strong>Phone:</strong>
                      <span>{prescriber.phone_number}</span>
                    </>
                  )}
                </div>
              </div>
            )}

            {/* Right: prescription image */}
            <div style={{ flexShrink: 0, width: "280px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.4rem" }}>
                <div style={{ fontSize: "0.85rem", fontWeight: 600, color: "var(--text-light)", textTransform: "uppercase", letterSpacing: "0.04em" }}>Image</div>
                <div style={{ display: "flex", gap: "0.4rem", alignItems: "center" }}>
                  {uploadingPicture && <span style={{ fontSize: "0.8rem", color: "var(--text-light)" }}>Uploading…</span>}
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="image/*"
                    style={{ display: "none" }}
                    onChange={handlePictureUpload}
                  />
                  <button
                    className="btn btn-primary"
                    style={{ padding: "2px 10px", fontSize: "0.8rem" }}
                    onClick={() => fileInputRef.current?.click()}
                    disabled={uploadingPicture}
                  >
                    {pictureUrl ? "Replace" : "+ Upload"}
                  </button>
                </div>
              </div>
              {pictureUrl ? (
                <img
                  src={pictureUrl}
                  alt="Prescription"
                  style={{ width: "100%", maxHeight: "240px", objectFit: "contain", borderRadius: "6px", border: "1px solid var(--border, #dee2e6)" }}
                />
              ) : (
                <div style={{
                  display: "flex", alignItems: "center", justifyContent: "center",
                  height: "120px", border: "2px dashed var(--border, #dee2e6)",
                  borderRadius: "6px", color: "var(--text-light)", fontSize: "0.9rem"
                }}>
                  No Image
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Drug Information */}
        <div>
          <h3 style={{ margin: "0 0 0.75rem 0", fontSize: "1.1rem" }}>Drug Information</h3>
          <div style={{ fontSize: "1.3rem", fontWeight: "bold", marginBottom: "0.5rem", color: "var(--primary)" }}>
            {prescription.drug.drug_name}
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: "0.25rem 1rem", marginBottom: "0.75rem" }}>
            <strong>NDC:</strong>
            <span style={{ fontFamily: "monospace" }}>{prescription.drug.ndc ?? "—"}</span>
            <strong>Manufacturer:</strong>
            <span>{prescription.drug.manufacturer}</span>
          </div>
          {prescription.drug.niosh && (
            <div style={{
              padding: "0.75rem",
              background: "rgba(239, 71, 111, 0.1)",
              border: "2px solid var(--danger)",
              borderRadius: "6px",
              fontWeight: "bold",
              fontSize: "0.9rem"
            }}>
              ⚠️ NIOSH HAZARDOUS DRUG — Special handling required
            </div>
          )}
        </div>
      </div>

      {/* Refill History */}
      {(() => {
        // If latest_refill is an active (in-progress) refill, prepend it as a synthetic row
        const activeRow: RefillHistoryItem | null =
          lr && lr.state && lr.state !== "SOLD" && lr.id != null
            ? {
                id: lr.id,
                quantity: lr.quantity,
                days_supply: lr.days_supply,
                completed_date: lr.completed_date,
                sold_date: lr.sold_date,
                total_cost: lr.total_cost ?? 0,
                copay_amount: lr.copay_amount,
                insurance_paid: lr.insurance_paid,
                insurance: lr.insurance,
                state: lr.state,
              }
            : null;

        const historyRows = prescription.refill_history ?? [];
        const activeAlreadyInHistory = activeRow != null && historyRows.some((h) => h.id === activeRow.id);
        const allRows: RefillHistoryItem[] = [
          ...(activeRow && !activeAlreadyInHistory ? [activeRow] : []),
          ...historyRows,
        ];

        const hasFills = allRows.length > 0 || lr != null;

        return (
          <div className="card vstack" style={{ gap: "0.5rem" }}>
            <h3 style={{ margin: 0 }}>Refill History</h3>
            {hasFills ? (
              <table className="table">
                <thead>
                  <tr>
                    <th>Fill #</th>
                    <th>Qty</th>
                    <th>Days Supply</th>
                    <th>Cash Price</th>
                    <th>Cost</th>
                    <th>Insurance</th>
                    <th>Filled</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {allRows.map((h) => {
                    const isActive = h.state != null && h.state !== "SOLD";
                    const planName = h.insurance?.insurance_company?.plan_name ?? null;
                    const patientCost = h.copay_amount != null ? Number(h.copay_amount) : Number(h.total_cost);

                    return (
                      <tr key={h.id} style={["QT","QV1","QP","QV2","READY"].includes(h.state ?? "") ? { background: "var(--primary-light, #e8f0fe)", borderLeft: "3px solid var(--primary)" } : undefined}>
                        <td><strong style={{ color: "var(--primary)" }}>{fillCountMap[h.id] ?? "—"}</strong></td>
                        <td>{h.quantity}</td>
                        <td>{h.days_supply}</td>
                        <td>${Number(h.total_cost).toFixed(2)}</td>
                        <td style={{ fontWeight: 600 }}>${patientCost.toFixed(2)}</td>
                        <td>{planName ?? "Cash"}</td>
                        <td>
                          {h.completed_date ? new Date(h.completed_date).toLocaleDateString() : "—"}
                          {isActive && h.state === "SCHEDULED" && lr?.due_date && (
                            <span style={{ marginLeft: "0.4rem", fontSize: "0.75rem", color: "var(--text-light)" }}>
                              (due {new Date(lr.due_date).toLocaleString(undefined, {
                                month: "short", day: "numeric", year: "numeric",
                                hour: "numeric", minute: "2-digit",
                              })}
                              {new Date(lr.due_date) < new Date() && (
                                <span style={{ color: "#ef476f", fontWeight: 600 }}> — overdue</span>
                              )})
                            </span>
                          )}
                        </td>
                        <td>
                          {h.sold_date
                            ? `Sold on ${new Date(h.sold_date).toLocaleDateString()}`
                            : isActive && h.state
                              ? <Badge state={h.state} />
                              : "—"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            ) : (
              <div style={{ color: "var(--text-light)" }}>No refills on file.</div>
            )}
          </div>
        );
      })()}

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

      {/* Sticky bottom bar */}
      <div style={{
        position: "sticky",
        bottom: 0,
        padding: "1rem",
        background: "var(--card)",
        borderTop: "2px solid var(--border)",
        display: "flex",
        gap: "1rem",
        justifyContent: "center",
        marginTop: "auto",
      }}>
        <button className="btn" onClick={onBack} style={{ minWidth: "120px" }}>
          ← Back
        </button>
        {canFill && (
          <button
            className="btn btn-primary"
            style={{ minWidth: "140px" }}
            onClick={onFill}
          >
            Fill Rx
          </button>
        )}
        {!isInactive && !isExpired && !hasRemainingQty && (!lr || !BLOCKING_FILL_STATES.has(lr.state)) && (
          <div style={{
            padding: "0.5rem 1rem",
            background: "rgba(239,68,68,0.1)",
            border: "1px solid var(--danger)",
            borderRadius: "6px",
            color: "var(--danger)",
            fontWeight: 600,
            fontSize: "0.9rem",
          }}>
            No remaining refills
          </div>
        )}
        {!isInactive && !isExpired && lr && HOLDABLE_STATES.has(lr.state) && (
          <button
            className="btn"
            style={{ background: "var(--warning, #f39c12)", color: "#fff", minWidth: "140px" }}
            onClick={() => setShowHold(true)}
          >
            Hold Rx
          </button>
        )}
        {!isInactive && !isExpired && (
          <button
            className="btn"
            style={{ background: "var(--danger)", color: "#fff", minWidth: "140px" }}
            onClick={() => setShowInactivate(true)}
          >
            Inactivate Rx
          </button>
        )}
      </div>
    </div>
  );
}
