import { useState, useEffect } from "react";
import { fillScript, getPrescribers, getPatientInsurance, calculateBilling } from "@/api";

const TIER_LABELS = { 1: "Tier 1 – Preferred Generic", 2: "Tier 2 – Preferred Brand", 3: "Tier 3 – Non-Preferred", 4: "Tier 4 – Specialty" };

/**
 * Determines if this is a new fill or a scheduled (early) refill.
 */
function getFillType(prescription) {
  const lr = prescription.latest_refill;
  if (!lr || !lr.sold_date) return "new_fill";
  if (lr.state) return "active";
  const daysSince = Math.floor(
    (Date.now() - new Date(lr.sold_date).getTime()) / (1000 * 60 * 60 * 24)
  );
  return daysSince > lr.days_supply - 7 ? "new_fill" : "schedule_refill";
}

function nextPickupDate(prescription) {
  const lr = prescription.latest_refill;
  if (!lr?.sold_date || lr.state) return "";
  const d = new Date(lr.sold_date);
  d.setDate(d.getDate() + lr.days_supply);
  return d.toISOString().split("T")[0];
}

function daysEarly(prescription) {
  const lr = prescription.latest_refill;
  if (!lr?.sold_date) return 0;
  const daysSince = Math.floor(
    (Date.now() - new Date(lr.sold_date).getTime()) / (1000 * 60 * 60 * 24)
  );
  return lr.days_supply - daysSince;
}

export default function FillScriptView({ prescription, patientName, patientId, onBack }) {
  const [prescribers, setPrescribers] = useState([]);
  const [patientInsurance, setPatientInsurance] = useState([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  // Billing state
  const [selectedInsuranceId, setSelectedInsuranceId] = useState("");
  const [billing, setBilling] = useState(null);   // BillingCalculateResponse
  const [billingLoading, setBillingLoading] = useState(false);

  const lr = prescription.latest_refill;
  const fillType = getFillType(prescription);
  const isScheduled = fillType === "schedule_refill";
  const recommendedDate = isScheduled ? nextPickupDate(prescription) : "";
  const early = isScheduled ? daysEarly(prescription) : 0;

  const [showEarlyModal, setShowEarlyModal] = useState(isScheduled);

  const [form, setForm] = useState({
    quantity: lr?.quantity ?? "",
    days_supply: lr?.days_supply ?? "",
    priority: "normal",
    initial_state: isScheduled ? "HOLD" : "QP",
    due_date: isScheduled ? nextPickupDate(prescription) : "",
  });

  useEffect(() => {
    getPrescribers().then(setPrescribers).catch(console.error);
    const pid = patientId ?? prescription.patient_id;
    if (pid) {
      getPatientInsurance(pid).then(setPatientInsurance).catch(console.error);
    }
  }, []);

  const prescriber = prescribers.find((p) => p.id === prescription.prescriber_id);

  // Recalculate billing whenever insurance or quantity/days_supply changes
  useEffect(() => {
    if (!selectedInsuranceId || !form.quantity || !form.days_supply) {
      setBilling(null);
      return;
    }
    setBillingLoading(true);
    calculateBilling({
      drug_id: prescription.drug_id,
      insurance_id: parseInt(selectedInsuranceId),
      quantity: parseInt(form.quantity),
      days_supply: parseInt(form.days_supply),
    })
      .then(setBilling)
      .catch(() => setBilling(null))
      .finally(() => setBillingLoading(false));
  }, [selectedInsuranceId, form.quantity, form.days_supply]);

  const handleChange = (e) => {
    setForm({ ...form, [e.target.name]: e.target.value });
  };

  const handleSchedule = () => setShowEarlyModal(false);

  const handleFillNow = () => {
    setForm((f) => ({ ...f, initial_state: "QP", due_date: "" }));
    setShowEarlyModal(false);
  };

  const handleSubmit = async () => {
    setSubmitting(true);
    setError("");
    try {
      const result = await fillScript(prescription.id, {
        quantity: parseInt(form.quantity),
        days_supply: parseInt(form.days_supply),
        priority: form.priority,
        initial_state: form.initial_state,
        due_date: form.due_date || null,
        insurance_id: selectedInsuranceId ? parseInt(selectedInsuranceId) : null,
      });

      let msg = `Fill created!\nRefill ID: ${result.refill_id}\nState: ${result.state}`;
      if (result.copay_amount != null) {
        msg += `\n\nBilling Summary:\n  Cash Price:      $${result.cash_price.toFixed(2)}\n  Patient Copay:   $${result.copay_amount.toFixed(2)}\n  Insurance Pays:  $${result.insurance_paid.toFixed(2)}`;
      }
      alert(msg);
      onBack();
    } catch (e) {
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  };

  const fillTypeBadge =
    fillType === "new_fill" ? (
      <span style={{ background: "var(--success)", color: "#fff", padding: "2px 10px", borderRadius: "4px", fontSize: "0.85rem" }}>
        New Fill
      </span>
    ) : fillType === "schedule_refill" ? (
      <span style={{ background: "var(--primary)", color: "#fff", padding: "2px 10px", borderRadius: "4px", fontSize: "0.85rem" }}>
        Schedule Refill
      </span>
    ) : (
      <span style={{ background: "#e67e22", color: "#fff", padding: "2px 10px", borderRadius: "4px", fontSize: "0.85rem" }}>
        Active Refill Exists
      </span>
    );

  const cashPrice = form.quantity && prescription.drug?.cost
    ? (parseFloat(prescription.drug.cost) * parseInt(form.quantity)).toFixed(2)
    : null;

  const activeInsurance = patientInsurance.filter(i => i.is_active);

  return (
    <div className="vstack">
      {showEarlyModal && (
        <div style={{
          position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)",
          display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000
        }}>
          <div className="card vstack" style={{ maxWidth: "420px", width: "90%", gap: "1rem", padding: "1.5rem" }}>
            <h3 style={{ margin: 0 }}>Prescription Too Soon to Fill</h3>
            <p style={{ margin: 0 }}>
              This prescription is <strong>{early} day{early !== 1 ? "s" : ""}</strong> early.
              The recommended fill date is <strong>{new Date(recommendedDate + "T00:00:00").toLocaleDateString()}</strong>.
            </p>
            <p style={{ margin: 0, color: "var(--text-light)", fontSize: "0.9rem" }}>
              Would you like to schedule it for the recommended date (placed on HOLD), or attempt to fill it right now?
            </p>
            <div style={{ display: "flex", gap: "1rem", justifyContent: "flex-end" }}>
              <button className="btn btn-secondary" onClick={onBack}>Cancel</button>
              <button className="btn btn-primary" onClick={handleSchedule}>
                Schedule for {new Date(recommendedDate + "T00:00:00").toLocaleDateString()}
              </button>
              <button className="btn btn-warning" onClick={handleFillNow}>Fill Now</button>
            </div>
          </div>
        </div>
      )}

      <div className="hstack" style={{ alignItems: "center", gap: "1rem" }}>
        <h2 style={{ margin: 0 }}>Fill Script</h2>
        {fillTypeBadge}
      </div>

      {/* Script summary */}
      <div className="card vstack" style={{ gap: "0.5rem" }}>
        <h3 style={{ margin: 0 }}>Script Details</h3>
        <div className="hstack" style={{ gap: "2rem", flexWrap: "wrap" }}>
          <div><strong>Patient:</strong> {patientName}</div>
          <div>
            <strong>Drug:</strong> {prescription.drug.drug_name} ({prescription.drug.manufacturer})
            {prescription.drug.niosh && (
              <span style={{ color: "var(--danger)", marginLeft: "0.5rem" }}>⚠ NIOSH</span>
            )}
          </div>
        </div>
        <div className="hstack" style={{ gap: "2rem", flexWrap: "wrap" }}>
          <div>
            <strong>Prescriber:</strong>{" "}
            {prescriber
              ? `Dr. ${prescriber.first_name} ${prescriber.last_name}${prescriber.specialty ? ` · ${prescriber.specialty}` : ""} (NPI: ${prescriber.npi})`
              : `ID ${prescription.prescriber_id}`}
          </div>
          <div><strong>Remaining Qty on Script:</strong> {prescription.remaining_quantity}</div>
          <div><strong>Brand Required:</strong> {prescription.brand_required ? "Yes" : "No"}</div>
        </div>

        {lr && (
          <div className="hstack" style={{ gap: "2rem", flexWrap: "wrap", color: "var(--text-light)", fontSize: "0.9rem", marginTop: "0.25rem" }}>
            <div><strong>Last Qty:</strong> {lr.quantity}</div>
            <div><strong>Last Days Supply:</strong> {lr.days_supply}</div>
            {lr.sold_date && (
              <div><strong>Last Sold:</strong> {new Date(lr.sold_date).toLocaleDateString()}</div>
            )}
            {lr.next_pickup && !lr.state && (
              <div><strong>Next Pickup:</strong> {new Date(lr.next_pickup).toLocaleDateString()}</div>
            )}
            {lr.state && (
              <div><strong>Current State:</strong> <span style={{ color: "var(--primary)" }}>{lr.state}</span></div>
            )}
          </div>
        )}
      </div>

      {fillType === "active" && (
        <div className="card" style={{ background: "rgba(230,126,34,0.1)", border: "2px solid #e67e22", padding: "1rem" }}>
          Warning: this prescription already has an active refill in state <strong>{lr?.state}</strong>.
          Proceeding will create a duplicate refill.
        </div>
      )}

      {fillType === "schedule_refill" && (
        <div className="card" style={{ background: "rgba(var(--primary-rgb, 52,152,219),0.08)", border: "1px solid var(--primary)", padding: "0.75rem" }}>
          This fill is early (patient is within their days supply). The due date has been pre-filled
          with the estimated next pickup date and the initial state set to <strong>HOLD</strong>.
          Adjust as needed.
        </div>
      )}

      {/* Fill Details */}
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

          <label>
            <strong>Initial State</strong>
            <select
              name="initial_state"
              value={form.initial_state}
              onChange={handleChange}
              style={{ width: "100%", padding: "0.5rem", marginTop: "0.25rem" }}
            >
              <option value="QP">QP (Prep/Fill)</option>
              <option value="HOLD">HOLD (On Hold)</option>
            </select>
          </label>

          <label style={{ gridColumn: "1 / -1" }}>
            <strong>Due Date{isScheduled ? " (estimated next pickup)" : " (optional)"}</strong>
            <input
              type="date"
              name="due_date"
              value={form.due_date}
              onChange={handleChange}
              style={{ width: "100%", padding: "0.5rem", marginTop: "0.25rem" }}
            />
          </label>
        </div>
      </div>

      {/* Billing / Insurance */}
      <div className="card vstack" style={{ gap: "1rem" }}>
        <h3 style={{ margin: 0 }}>Billing</h3>

        {/* Cash price always shown */}
        {cashPrice && (
          <div className="hstack" style={{ gap: "2rem", flexWrap: "wrap", alignItems: "center" }}>
            <div style={{ fontSize: "1rem" }}>
              <strong>Cash Price:</strong>{" "}
              <span style={{ fontSize: "1.2rem", fontWeight: 700 }}>${cashPrice}</span>
              <span style={{ color: "var(--text-light)", fontSize: "0.85rem", marginLeft: "0.5rem" }}>
                ({form.quantity} × ${parseFloat(prescription.drug.cost).toFixed(2)})
              </span>
            </div>
          </div>
        )}

        {/* Insurance dropdown */}
        <label>
          <strong>Bill to Insurance</strong>
          <select
            value={selectedInsuranceId}
            onChange={(e) => { setSelectedInsuranceId(e.target.value); setBilling(null); }}
            style={{ width: "100%", padding: "0.5rem", marginTop: "0.25rem" }}
          >
            <option value="">— Cash / No Insurance —</option>
            {activeInsurance.map((ins) => (
              <option key={ins.id} value={ins.id}>
                {ins.insurance_company.plan_name} · {ins.insurance_company.plan_id}
                {ins.is_primary ? " (Primary)" : " (Secondary)"}
              </option>
            ))}
          </select>
          {activeInsurance.length === 0 && (
            <div style={{ color: "var(--text-light)", fontSize: "0.85rem", marginTop: "0.25rem" }}>
              No insurance on file for this patient.
            </div>
          )}
        </label>

        {/* Insurance price breakdown */}
        {selectedInsuranceId && (
          <div style={{
            background: "var(--surface, #f8f9fa)",
            border: "1px solid var(--border, #dee2e6)",
            borderRadius: "6px",
            padding: "0.75rem 1rem",
          }}>
            {billingLoading && <div style={{ color: "var(--text-light)" }}>Calculating…</div>}
            {!billingLoading && billing && (
              billing.not_covered ? (
                <div style={{ color: "var(--danger)" }}>
                  <strong>Not Covered</strong> — {billing.plan_name} does not cover this drug.
                  Patient pays full cash price: <strong>${parseFloat(billing.cash_price).toFixed(2)}</strong>
                </div>
              ) : (
                <div className="vstack" style={{ gap: "0.4rem" }}>
                  <div style={{ fontWeight: 600, marginBottom: "0.25rem" }}>
                    {billing.plan_name} · {TIER_LABELS[billing.tier] ?? `Tier ${billing.tier}`}
                  </div>
                  <div className="hstack" style={{ gap: "2rem", flexWrap: "wrap" }}>
                    <div>
                      <span style={{ color: "var(--text-light)", fontSize: "0.85rem" }}>Cash Price</span>
                      <div style={{ fontSize: "1.1rem", textDecoration: "line-through", color: "var(--text-light)" }}>
                        ${parseFloat(billing.cash_price).toFixed(2)}
                      </div>
                    </div>
                    <div>
                      <span style={{ color: "var(--text-light)", fontSize: "0.85rem" }}>Insurance Pays</span>
                      <div style={{ fontSize: "1.1rem", color: "var(--success, #27ae60)", fontWeight: 600 }}>
                        ${parseFloat(billing.insurance_paid).toFixed(2)}
                      </div>
                    </div>
                    <div>
                      <span style={{ color: "var(--text-light)", fontSize: "0.85rem" }}>Patient Copay</span>
                      <div style={{ fontSize: "1.4rem", fontWeight: 700, color: "var(--primary)" }}>
                        ${parseFloat(billing.insurance_price).toFixed(2)}
                      </div>
                    </div>
                  </div>
                </div>
              )
            )}
            {!billingLoading && !billing && (
              <div style={{ color: "var(--text-light)", fontSize: "0.85rem" }}>
                Enter quantity and days supply to calculate insurance price.
              </div>
            )}
          </div>
        )}
      </div>

      {error && <p style={{ color: "var(--danger)", margin: 0 }}>{error}</p>}

      <div style={{ display: "flex", gap: "1rem" }}>
        <button className="btn btn-secondary" onClick={onBack}>
          Back
        </button>
        <button
          className="btn btn-success"
          onClick={handleSubmit}
          disabled={submitting || !form.quantity || !form.days_supply}
        >
          {submitting ? "Creating..." : "Create Fill"}
        </button>
      </div>
    </div>
  );
}
