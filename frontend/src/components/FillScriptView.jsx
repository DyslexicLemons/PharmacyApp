import { useState, useEffect } from "react";
import { fillScript, getPrescribers, getPatientInsurance, calculateBilling } from "@/api";

const TIER_LABELS = {
  1: "Tier 1 – Preferred Generic",
  2: "Tier 2 – Preferred Brand",
  3: "Tier 3 – Non-Preferred",
  4: "Tier 4 – Specialty"
};

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

  const [selectedInsuranceId, setSelectedInsuranceId] = useState("");
  const [billing, setBilling] = useState(null);
  const [billingLoading, setBillingLoading] = useState(false);

  const lr = prescription.latest_refill;
  const fillType = getFillType(prescription);

  const isScheduled = fillType === "schedule_refill";
  const recommendedDate = isScheduled ? nextPickupDate(prescription) : "";
  const early = isScheduled ? daysEarly(prescription) : 0;

  const [showEarlyModal, setShowEarlyModal] = useState(isScheduled);

  const isExhausted = prescription.remaining_quantity <= 0;

  const [form, setForm] = useState({
    quantity: lr?.quantity ?? "",
    days_supply: lr?.days_supply ?? "",
    priority: "normal",
    scheduled: isScheduled,
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

    const { name, value } = e.target;

    if (name === "quantity") {

      const qty = parseInt(value);

      if (qty > prescription.remaining_quantity) {
        setForm({
          ...form,
          quantity: prescription.remaining_quantity
        });
        return;
      }
    }

    setForm({
      ...form,
      [name]: value
    });
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

    const qty = parseInt(form.quantity);
    const days = parseInt(form.days_supply);

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

    setSubmitting(true);
    setError("");

    try {

      const result = await fillScript(prescription.id, {
        quantity: qty,
        days_supply: parseInt(form.days_supply),
        priority: form.priority,
        scheduled: form.scheduled,
        due_date: form.due_date || null,
        insurance_id: selectedInsuranceId ? parseInt(selectedInsuranceId) : null,
      });

      let msg = `Fill created!\nRefill ID: ${result.refill_id}\nState: ${result.state}`;

      if (result.copay_amount != null) {
        msg += `\n\nBilling Summary:
Cash Price:      $${result.cash_price.toFixed(2)}
Patient Copay:   $${result.copay_amount.toFixed(2)}
Insurance Pays:  $${result.insurance_paid.toFixed(2)}`;
      }

      alert(msg);
      onBack();

    } catch (e) {

      setError(e.message);

    } finally {

      setSubmitting(false);

    }
  };

  const cashPrice =
    form.quantity && prescription.drug?.cost
      ? (parseFloat(prescription.drug.cost) * parseInt(form.quantity)).toFixed(2)
      : null;

  const activeInsurance = patientInsurance.filter(i => i.is_active);

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
          <div><strong>Rx #:</strong> {'17' + String(prescription.id).padStart(5, '0')}</div>
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