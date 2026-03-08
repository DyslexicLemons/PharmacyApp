import { useState, useEffect } from "react";
import { getPatients, getDrugs, getPrescribers } from "@/api";

const API = import.meta.env.VITE_API_BASE || 'http://localhost:8000';

export default function PrescriptionForm({ onBack }) {
  const [step, setStep] = useState(1); // Multi-step form
  const [patients, setPatients] = useState([]);
  const [drugs, setDrugs] = useState([]);
  const [prescribers, setPrescribers] = useState([]);
  const [conflict, setConflict] = useState(null);

  const [form, setForm] = useState({
    patient_id: "",
    drug_id: "",
    prescriber_id: "",
    quantity: "",
    days_supply: "",
    total_refills: "1",
    brand_required: false,
    priority: "normal",
    initial_state: "QP",
    due_date: "",
  });

  useEffect(() => {
    // Load patients, drugs, prescribers
    getPatients().then(setPatients).catch(console.error);
    getDrugs().then(setDrugs).catch(console.error);
    getPrescribers().then(setPrescribers).catch(console.error);
  }, []);

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    setForm({ ...form, [name]: type === "checkbox" ? checked : value });
  };

  const checkConflict = async () => {
    if (!form.patient_id || !form.drug_id) {
      alert("Please select patient and drug first");
      return;
    }

    try {
      const res = await fetch(
        `${API}/refills/check_conflict?patient_id=${form.patient_id}&drug_id=${form.drug_id}`
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

  const handleSubmit = async () => {
    try {
      const res = await fetch(`${API}/refills/create_manual`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          patient_id: parseInt(form.patient_id),
          drug_id: parseInt(form.drug_id),
          prescriber_id: parseInt(form.prescriber_id),
          quantity: parseInt(form.quantity),
          days_supply: parseInt(form.days_supply),
          total_refills: parseInt(form.total_refills),
          brand_required: form.brand_required,
          priority: form.priority,
          initial_state: form.initial_state,
          due_date: form.due_date || null,
        }),
      });

      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || "Failed to create prescription");
      }

      const result = await res.json();
      alert(`Prescription created successfully!\nRefill ID: ${result.refill_id}\nState: ${result.state}`);

      // Reset form
      setForm({
        patient_id: "",
        drug_id: "",
        prescriber_id: "",
        quantity: "",
        days_supply: "",
        total_refills: "1",
        brand_required: false,
        priority: "normal",
        initial_state: "QP",
        due_date: "",
      });
      setStep(1);
      setConflict(null);

      if (onBack) onBack();
    } catch (e) {
      alert(e.message);
    }
  };

  const selectedPatient = patients.find(p => p.id === parseInt(form.patient_id));
  const selectedDrug = drugs.find(d => d.id === parseInt(form.drug_id));
  const selectedPrescriber = prescribers.find(p => p.id === parseInt(form.prescriber_id));

  return (
    <div className="vstack">
      <h2>Create Manual Prescription</h2>
      <p style={{ color: "var(--text-light)", marginBottom: "1rem" }}>
        Manual prescriptions bypass QT triage and go directly to {form.initial_state}
      </p>

      {step === 1 && (
        <div className="vstack" style={{ gap: "1rem" }}>
          <h3>Step 1: Select Patient & Drug</h3>

          <div className="card" style={{ padding: "1rem" }}>
            <label>
              <strong>Patient</strong>
              <select
                name="patient_id"
                value={form.patient_id}
                onChange={handleChange}
                style={{ width: "100%", padding: "0.5rem", marginTop: "0.25rem" }}
              >
                <option value="">-- Select Patient --</option>
                {patients.map(p => (
                  <option key={p.id} value={p.id}>
                    {p.last_name}, {p.first_name} (DOB: {p.dob})
                  </option>
                ))}
              </select>
            </label>

            {selectedPatient && (
              <div style={{ marginTop: "0.5rem", padding: "0.5rem", background: "var(--bg-light)", borderRadius: "4px" }}>
                <strong>{selectedPatient.first_name} {selectedPatient.last_name}</strong>
                <div style={{ fontSize: "0.9rem", color: "var(--text-light)" }}>
                  DOB: {selectedPatient.dob} | {selectedPatient.address}
                </div>
              </div>
            )}
          </div>

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
            disabled={!form.patient_id || !form.drug_id}
          >
            Check for Conflicts & Continue →
          </button>
        </div>
      )}

      {step === 2 && (
        <div className="vstack" style={{ gap: "1rem" }}>
          <h3>Step 2: Prescription Details</h3>

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
              <strong>Due Date (optional)</strong>
              <input
                type="date"
                name="due_date"
                value={form.due_date}
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

            <label style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <input
                type="checkbox"
                name="brand_required"
                checked={form.brand_required}
                onChange={handleChange}
              />
              <strong>Brand Required</strong>
            </label>
          </div>

          <div style={{ display: "flex", gap: "1rem" }}>
            <button
              className="btn btn-secondary"
              onClick={() => setStep(1)}
            >
              ← Back
            </button>
            <button
              className="btn btn-success"
              onClick={handleSubmit}
              disabled={!form.prescriber_id || !form.quantity || !form.days_supply}
            >
              Create Prescription
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
