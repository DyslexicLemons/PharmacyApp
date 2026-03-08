import { useState } from "react";
import { createPatient } from "@/api";

export default function NewPatientForm({ prefillLast, prefillFirst, onCreated, onBack }) {
  const [form, setForm] = useState({
    first_name: prefillFirst || "",
    last_name: prefillLast || "",
    dob: "",
    address: "",
  });
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  function handleChange(e) {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      const patient = await createPatient(form);
      onCreated(patient);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  const ready = form.first_name.trim() && form.last_name.trim() && form.dob && form.address.trim();

  return (
    <div className="vstack">
      <h2>New Patient</h2>

      <form className="vstack" style={{ gap: "1rem" }} onSubmit={handleSubmit}>
        <div className="card" style={{ padding: "1rem", display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
          <label>
            <strong>Last Name <span style={{ color: "var(--danger)" }}>*</span></strong>
            <input
              autoFocus
              className="input"
              name="last_name"
              value={form.last_name}
              onChange={handleChange}
              required
              style={{ width: "100%", padding: "0.5rem", marginTop: "0.25rem" }}
            />
          </label>

          <label>
            <strong>First Name <span style={{ color: "var(--danger)" }}>*</span></strong>
            <input
              className="input"
              name="first_name"
              value={form.first_name}
              onChange={handleChange}
              required
              style={{ width: "100%", padding: "0.5rem", marginTop: "0.25rem" }}
            />
          </label>

          <label>
            <strong>Date of Birth <span style={{ color: "var(--danger)" }}>*</span></strong>
            <input
              type="date"
              className="input"
              name="dob"
              value={form.dob}
              onChange={handleChange}
              required
              style={{ width: "100%", padding: "0.5rem", marginTop: "0.25rem" }}
            />
          </label>

          <label>
            <strong>Address <span style={{ color: "var(--danger)" }}>*</span></strong>
            <input
              className="input"
              name="address"
              value={form.address}
              onChange={handleChange}
              required
              style={{ width: "100%", padding: "0.5rem", marginTop: "0.25rem" }}
            />
          </label>
        </div>

        {error && (
          <div style={{ color: "var(--danger)", fontSize: "0.9rem" }}>{error}</div>
        )}

        <div style={{ display: "flex", gap: "1rem" }}>
          <button type="button" className="btn btn-secondary" onClick={onBack}>
            ← Cancel
          </button>
          <button
            type="submit"
            className="btn btn-success"
            disabled={!ready || submitting}
          >
            {submitting ? "Saving..." : "Create Patient"}
          </button>
        </div>
      </form>
    </div>
  );
}
