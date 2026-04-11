import React, { useContext, useState, useEffect, useMemo } from "react";
import { fillScript, getPrescribers, getPatientInsurance, calculateBilling } from "@/api";
import { AuthContext } from "@/context/AuthContext";
import { useNotification } from "@/context/NotificationContext";
import { usePrescriptionLock } from "@/hooks/usePrescriptionLock";
import type { Prescriber, BillingResult, Prescription } from "@/types";

// Extended prescription type with runtime fields not in the base type
interface LatestRefill {
  quantity: number;
  days_supply: number;
  sold_date?: string | null;
  state?: string | null;
}

interface PrescriptionWithRuntime {
  id: number;
  remaining_quantity: number;
  instructions: string | null;
  drug_id: number;
  patient_id?: number;
  prescriber_id?: number;
  drug: { drug_name: string; manufacturer: string; niosh?: boolean; cost?: number | string };
  latest_refill?: LatestRefill | null;
}

interface PatientInsuranceItem {
  id: number;
  is_active: boolean;
  [key: string]: unknown;
}

interface FillForm {
  quantity: number | string;
  days_supply: number | string;
  priority: string;
  scheduled: boolean;
  due_date: string;
}

function parseDueTimeInput(raw: string): { hours: number; minutes: number } | null {
  const str = raw.trim().toLowerCase();
  const now = new Date();

  // single unit: 30m, 2h, 1.5h
  const single = str.match(/^(\d+(?:\.\d+)?)(m|h)$/);
  if (single) {
    const amount = parseFloat(single[1]);
    const unit = single[2];
    const ms = unit === "m" ? amount * 60 * 1000 : amount * 60 * 60 * 1000;
    const result = new Date(now.getTime() + ms);
    return { hours: result.getHours(), minutes: result.getMinutes() };
  }

  // compound: 1h 30m or 1h30m
  const compound = str.match(/^(\d+)h\s*(\d+)m$/);
  if (compound) {
    const ms = (parseInt(compound[1]) * 60 + parseInt(compound[2])) * 60 * 1000;
    const result = new Date(now.getTime() + ms);
    return { hours: result.getHours(), minutes: result.getMinutes() };
  }

  return null;
}

function formatTimeDisplay(hours: number, minutes: number): string {
  const d = new Date();
  d.setHours(hours, minutes, 0, 0);
  return d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

function daysFromToday(dateStr: string): number {
  const due = new Date(dateStr + "T00:00:00");
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return (due.getTime() - today.getTime()) / (1000 * 60 * 60 * 24);
}

function getFillType(prescription: PrescriptionWithRuntime): string {
  const lr = prescription.latest_refill;
  if (!lr || !lr.sold_date) return "new_fill";
  if (lr.state) return "active";

  const daysSince = Math.floor(
    (Date.now() - new Date(lr.sold_date).getTime()) / (1000 * 60 * 60 * 24)
  );

  return daysSince > lr.days_supply - 7 ? "new_fill" : "schedule_refill";
}

function nextPickupDate(prescription: PrescriptionWithRuntime): string {
  const lr = prescription.latest_refill;
  if (!lr?.sold_date || lr.state) return "";

  const d = new Date(lr.sold_date);
  d.setDate(d.getDate() + lr.days_supply);

  return d.toISOString().split("T")[0];
}

function daysEarly(prescription: PrescriptionWithRuntime): number {
  const lr = prescription.latest_refill;
  if (!lr?.sold_date) return 0;

  const daysSince = Math.floor(
    (Date.now() - new Date(lr.sold_date).getTime()) / (1000 * 60 * 60 * 24)
  );

  return lr.days_supply - daysSince;
}

interface FillScriptViewProps {
  prescription: Prescription;
  patientName: string;
  patientId?: number;
  onBack: () => void;
  onSuccess?: () => void;
}

export default function FillScriptView({ prescription: rawPrescription, patientName, patientId, onBack, onSuccess }: FillScriptViewProps) {
  const prescription = rawPrescription as unknown as PrescriptionWithRuntime;
  const { token } = useContext(AuthContext);
  const { addNotification } = useNotification();
  const { lockError, lockPending } = usePrescriptionLock(prescription.id);
  const [prescribers, setPrescribers] = useState<Prescriber[]>([]);
  const [patientInsurance, setPatientInsurance] = useState<PatientInsuranceItem[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const [selectedInsuranceId, setSelectedInsuranceId] = useState("");
  const [billing, setBilling] = useState<BillingResult | null>(null);
  const [billingLoading, setBillingLoading] = useState(false);

  const lr = prescription.latest_refill;
  const fillType = getFillType(prescription);

  const isScheduled = fillType === "schedule_refill";
  const recommendedDate = isScheduled ? nextPickupDate(prescription) : "";
  const early = isScheduled ? daysEarly(prescription) : 0;

  const defaultFillTime = useMemo(() => {
    const oneHour = new Date(Date.now() + 60 * 60 * 1000);
    return { hours: oneHour.getHours(), minutes: oneHour.getMinutes() };
  }, []);

  const [dueTimeInput, setDueTimeInput] = useState(!isScheduled ? "1h" : "");
  const [dueTimeDisplay, setDueTimeDisplay] = useState(
    !isScheduled ? formatTimeDisplay(defaultFillTime.hours, defaultFillTime.minutes) : ""
  );
  const [resolvedTime, setResolvedTime] = useState<{ hours: number; minutes: number } | null>(
    !isScheduled ? defaultFillTime : null
  );

  const [showEarlyModal, setShowEarlyModal] = useState(isScheduled);

  const isExhausted = prescription.remaining_quantity <= 0;

  const [form, setForm] = useState<FillForm>({
    quantity: lr?.quantity ?? "",
    days_supply: lr?.days_supply ?? "",
    priority: "normal",
    scheduled: isScheduled,
    due_date: isScheduled ? nextPickupDate(prescription) : "",
  });

  const isScheduledDate = useMemo(() => {
    if (!form.due_date) return false;
    return daysFromToday(form.due_date) > 7;
  }, [form.due_date]);

  useEffect(() => {
    if (!token) return;
    getPrescribers(token)
      .then((res) => setPrescribers(Array.isArray(res) ? res : res.items))
      .catch(console.error);

    const pid = patientId ?? prescription.patient_id;
    if (pid) {
      getPatientInsurance(pid, token)
        .then((res) => setPatientInsurance(res as unknown as PatientInsuranceItem[]))
        .catch(console.error);
    }
  }, [token]);

  const prescriber = prescribers.find((p) => p.id === prescription.prescriber_id);

  useEffect(() => {
    if (!selectedInsuranceId || !form.quantity || !form.days_supply) {
      setBilling(null);
      return;
    }

    setBillingLoading(true);

    if (!token) { setBillingLoading(false); return; }
    calculateBilling({
      drug_id: prescription.drug_id,
      insurance_id: parseInt(selectedInsuranceId),
      quantity: parseInt(String(form.quantity)),
      days_supply: parseInt(String(form.days_supply)),
    }, token)
      .then(setBilling)
      .catch(() => setBilling(null))
      .finally(() => setBillingLoading(false));

  }, [selectedInsuranceId, form.quantity, form.days_supply]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = e.target;

    if (name === "quantity") {
      const qty = parseInt(value);
      if (qty > prescription.remaining_quantity) {
        setForm({ ...form, quantity: prescription.remaining_quantity });
        return;
      }
    }

    if (name === "due_date") {
      const willBeScheduled = value ? daysFromToday(value) > 7 : false;
      setForm({ ...form, due_date: value, scheduled: willBeScheduled });
      if (willBeScheduled) {
        setDueTimeInput("");
        setDueTimeDisplay("");
        setResolvedTime(null);
      }
      return;
    }

    setForm({ ...form, [name]: value });
  };

  const handleSchedule = () => setShowEarlyModal(false);

  const handleFillNow = () => {
    setForm((f) => ({
      ...f,
      scheduled: false,
      due_date: ""
    }));
    setShowEarlyModal(false);
  };

  const handleSubmit = async () => {
    const qty = parseInt(String(form.quantity));
    const days = parseInt(String(form.days_supply));

    if (!qty || qty <= 0) {
      setError("Quantity must be greater than 0.");
      return;
    }

    if (!days || days <= 0) {
      setError("Days supply must be greater than 0.");
      return;
    }

    if (qty > prescription.remaining_quantity) {
      setError(
        `Quantity exceeds remaining authorized amount (${prescription.remaining_quantity}).`
      );
      return;
    }

    if (!token) { setError("Not authenticated."); return; }
    setSubmitting(true);
    setError("");

    try {
      let dueDateTime: string | null = null;
      if (form.due_date) {
        let timeParsed = resolvedTime;
        if (!timeParsed && !isScheduledDate && dueTimeInput.trim()) {
          timeParsed = parseDueTimeInput(dueTimeInput);
        }
        if (!timeParsed && !isScheduledDate) {
          const oneHour = new Date(Date.now() + 60 * 60 * 1000);
          timeParsed = { hours: oneHour.getHours(), minutes: oneHour.getMinutes() };
        }
        if (timeParsed && !isScheduledDate) {
          const combined = new Date(form.due_date + "T00:00:00");
          combined.setHours(timeParsed.hours, timeParsed.minutes, 0, 0);
          dueDateTime = combined.toISOString();
        } else {
          dueDateTime = form.due_date;
        }
      }

      const result = await fillScript(prescription.id, {
        quantity: qty,
        days_supply: parseInt(String(form.days_supply)),
        priority: form.priority,
        scheduled: form.scheduled,
        due_date: dueDateTime,
        insurance_id: selectedInsuranceId ? parseInt(selectedInsuranceId) : null,
      }, token);

      const stateLabel = String(result.state).split('.').pop() ?? result.state;
      let msg = `Fill created!\nRX#: ${prescription.id}\nState: ${stateLabel}`;

      if ((result as unknown as Record<string, unknown>).copay_amount != null) {
        const r = result as unknown as Record<string, number>;
        msg += `\n\nBilling Summary:\nCash Price:      $${r.cash_price.toFixed(2)}\nPatient Copay:   $${r.copay_amount.toFixed(2)}\nInsurance Pays:  $${r.insurance_paid.toFixed(2)}`;
      }

      addNotification(msg, "success");
      (onSuccess ?? onBack)();

    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  const cashPrice =
    form.quantity && prescription.drug?.cost
      ? (parseFloat(String(prescription.drug.cost)) * parseInt(String(form.quantity))).toFixed(2)
      : null;

  const activeInsurance = patientInsurance.filter(i => i.is_active);

  if (lockPending) return null;

  if (lockError) {
    return (
      <div className="vstack" style={{ alignItems: "center", justifyContent: "center", padding: "3rem", gap: "1rem" }}>
        <span style={{ fontSize: "2rem" }}>🔒</span>
        <p style={{ fontWeight: 600, textAlign: "center" }}>{lockError}</p>
        <button className="btn" onClick={onBack}>Go Back</button>
      </div>
    );
  }

  return (
    <div className="vstack">
      <div className="hstack" style={{ alignItems: "center", gap: "1rem" }}>
        <h2 style={{ margin: 0 }}>Fill Script</h2>
      </div>

      {prescription.drug?.niosh && (
        <div style={{
          padding: "0.85rem 1rem",
          background: "rgba(239, 71, 111, 0.12)",
          border: "2px solid var(--danger)",
          borderRadius: "8px",
          fontWeight: "bold",
          fontSize: "0.95rem",
          color: "var(--danger)"
        }}>
          ⚠️ NIOSH HAZARDOUS DRUG — Special handling and PPE required before dispensing.
        </div>
      )}

      <div className="card vstack" style={{ gap: "0.5rem" }}>
        <h3 style={{ margin: 0 }}>Script Details</h3>

        <div className="hstack" style={{ gap: "2rem", flexWrap: "wrap" }}>
          <div><strong>Rx #:</strong> {prescription.id}</div>
          <div><strong>Patient:</strong> {patientName}</div>
          <div>
            <strong>Drug:</strong> {prescription.drug.drug_name} ({prescription.drug.manufacturer})
          </div>
        </div>

        <div className="hstack" style={{ gap: "2rem", flexWrap: "wrap" }}>
          <div>
            {prescription.instructions}
          </div>
        </div>

        <div className="hstack" style={{ gap: "2rem", flexWrap: "wrap" }}>
          <div>
            <strong>Remaining Qty on Script:</strong> {prescription.remaining_quantity}
          </div>
        </div>
      </div>

      <div className="card vstack" style={{ gap: "1rem" }}>
        <h3 style={{ margin: 0 }}>Fill Details</h3>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
          <label>
            <strong>Quantity</strong>
            <input
              type="number"
              name="quantity"
              value={form.quantity}
              onChange={handleChange}
              min="1"
              max={prescription.remaining_quantity}
              style={{ width: "100%", padding: "0.5rem", marginTop: "0.25rem" }}
            />
            <div style={{ color: "var(--text-light)", fontSize: "0.85rem" }}>
              Qty remaining: {prescription.remaining_quantity}
            </div>
          </label>

          <label>
            <strong>Days Supply</strong>
            <input
              type="number"
              name="days_supply"
              value={form.days_supply}
              onChange={handleChange}
              min="1"
              style={{ width: "100%", padding: "0.5rem", marginTop: "0.25rem" }}
            />
          </label>

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

          <label style={{ gridColumn: "1 / -1" }}>
            <strong>Due Date</strong>
            <input
              type="date"
              name="due_date"
              value={form.due_date}
              onChange={handleChange}
              style={{ width: "100%", padding: "0.5rem", marginTop: "0.25rem" }}
            />
          </label>

          <div style={{ gridColumn: "1 / -1" }}>
            <strong>Due Time</strong>
            {isScheduledDate ? (
              <div style={{ marginTop: "0.4rem" }}>
                <div style={{
                  padding: "0.65rem 1rem",
                  background: "rgba(99,102,241,0.08)",
                  border: "1px solid var(--primary)",
                  borderRadius: "6px",
                  fontSize: "0.9rem",
                  marginBottom: "0.5rem",
                }}>
                  Schedule script for{" "}
                  <strong>
                    {new Date(form.due_date + "T00:00:00").toLocaleDateString(undefined, {
                      month: "long", day: "numeric", year: "numeric",
                    })}
                  </strong>?
                </div>
                <input
                  className="input"
                  placeholder="e.g. 1h, 30m"
                  value=""
                  disabled
                  style={{ width: "120px", padding: "0.5rem", opacity: 0.35, cursor: "not-allowed" }}
                />
              </div>
            ) : (
              <>
                <div style={{ fontSize: "0.85rem", color: "var(--text-light)", marginTop: "0.25rem" }}>
                  <code>30m</code> = 30 min from now &nbsp;|&nbsp;
                  <code>1h</code> = 1 hour from now &nbsp;|&nbsp;
                  <code>2h 30m</code> = 2½ hours from now
                </div>
                <div style={{ display: "flex", gap: "0.75rem", alignItems: "center", marginTop: "0.4rem" }}>
                  <input
                    className="input"
                    placeholder="e.g. 1h, 30m"
                    value={dueTimeInput}
                    onChange={(e) => {
                      const raw = e.target.value;
                      setDueTimeInput(raw);
                      setResolvedTime(null);
                      if (!raw.trim()) {
                        setDueTimeDisplay("");
                        return;
                      }
                      const parsed = parseDueTimeInput(raw);
                      if (parsed) {
                        setDueTimeDisplay(formatTimeDisplay(parsed.hours, parsed.minutes));
                      } else {
                        setDueTimeDisplay("Invalid (e.g. 30m, 2h)");
                      }
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        const parsed = parseDueTimeInput(dueTimeInput);
                        if (parsed) {
                          const display = formatTimeDisplay(parsed.hours, parsed.minutes);
                          setResolvedTime(parsed);
                          setDueTimeInput(display);
                          setDueTimeDisplay("✓ Set");
                        }
                      }
                    }}
                    style={{ width: "120px", padding: "0.5rem" }}
                  />
                  {dueTimeDisplay && (
                    <span style={{
                      fontSize: "0.9rem",
                      color: resolvedTime || dueTimeDisplay === "✓ Set"
                        ? "var(--success, #06d6a0)"
                        : dueTimeDisplay.startsWith("Invalid") ? "var(--danger)" : "var(--success, #06d6a0)",
                      fontWeight: 500,
                    }}>
                      {dueTimeDisplay.startsWith("Invalid") ? dueTimeDisplay : dueTimeDisplay === "✓ Set" ? "✓ Set" : `→ ${dueTimeDisplay}`}
                    </span>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      {error && <p style={{ color: "var(--danger)", margin: 0 }}>{error}</p>}

      <div style={{ display: "flex", gap: "1rem" }}>
        <button
          className="btn btn-secondary"
          onClick={onBack}
        >
          Back
        </button>

        <button
          className="btn btn-success"
          onClick={handleSubmit}
          disabled={
            submitting ||
            !form.quantity ||
            !form.days_supply ||
            isExhausted
          }
        >
          {submitting ? "Creating..." : "Create Fill"}
        </button>
      </div>
    </div>
  );
}
