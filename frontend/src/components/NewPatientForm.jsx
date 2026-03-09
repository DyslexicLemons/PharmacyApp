import { useState, useContext } from "react";
import { AuthContext } from "@/context/AuthContext";
import { createPatient } from "@/api";

export default function NewPatientForm({ prefillLast, prefillFirst, onCreated, onBack }) {
  const { token } = useContext(AuthContext);
  const UPPERCASE_FIELDS = ["first_name", "last_name", "address", "city", "state"];

  const [form, setForm] = useState({
    first_name: (prefillFirst || "").toUpperCase(),
    last_name: (prefillLast || "").toUpperCase(),
    dob: "",
    address: "",
    city: "",
    state: "",
  });
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  function handleChange(e) {
    const { name, value } = e.target;
    setForm((prev) => ({
      ...prev,
      [name]: UPPERCASE_FIELDS.includes(name) ? value.toUpperCase() : value,
    }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      const patient = await createPatient(form, token);
      onCreated(patient);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  const ready = form.first_name.trim() && form.last_name.trim() && form.dob && form.address.trim() && form.city.trim() && form.state.trim();

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

          <label>
            <strong>City <span style={{ color: "var(--danger)" }}>*</span></strong>
            <input
              className="input"
              name="city"
              value={form.city}
              onChange={handleChange}
              required
              style={{ width: "100%", padding: "0.5rem", marginTop: "0.25rem" }}
            />
          </label>

          <label>
            <strong>State <span style={{ color: "var(--danger)" }}>*</span></strong>
            <input
              className="input"
              name="state"
              value={form.state}
              onChange={handleChange}
              required
              maxLength={2}
              placeholder="e.g. TX"
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
