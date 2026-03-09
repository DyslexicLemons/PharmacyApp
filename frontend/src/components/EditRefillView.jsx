import { useContext, useEffect, useState } from "react";
import { getRefill, editRefill } from "@/api";
import { AuthContext } from "@/context/AuthContext";

const PRIORITIES = ["low", "normal", "high", "stat"];

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

export default function EditRefillView({ refillId, onBack, onSaved }) {
  const { token } = useContext(AuthContext);
  const [refill, setRefill] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  // Form fields
  const [quantity, setQuantity] = useState("");
  const [daysSupply, setDaysSupply] = useState("");
  const [priority, setPriority] = useState("normal");
  const [dueDate, setDueDate] = useState("");
  const [instructions, setInstructions] = useState("");
  const [dawCode, setDawCode] = useState(0);

  useEffect(() => {
    getRefill(refillId, token)
      .then((r) => {
        setRefill(r);
        setQuantity(String(r.quantity));
        setDaysSupply(String(r.days_supply));
        setPriority(r.priority);
        setDueDate(r.due_date);
        setInstructions(r.prescription.instructions || "");
        setDawCode(r.prescription.daw_code ?? 0);
        setError("");
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [refillId]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError("");

    const payload = {
      quantity: parseInt(quantity, 10),
      days_supply: parseInt(daysSupply, 10),
      priority,
      due_date: dueDate,
      instructions,
      daw_code: dawCode,
    };

    try {
      const updated = await editRefill(refillId, payload, token);
      const msg =
        updated.state === "QV1"
          ? "Script saved and sent back to QV1 for re-verification."
          : "Script saved and returned to QT for triage.";
      alert(msg);
      if (onSaved) onSaved(updated);
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div className="vstack"><p>Loading...</p></div>;
  if (error && !refill) return <div className="vstack"><p style={{ color: "var(--danger)" }}>{error}</p></div>;
  if (!refill) return <div className="vstack"><p>Refill not found</p></div>;

  const priorState = refill.state;
  const newStateLabel = priorState === "QP" ? "QV1" : "QT";

  return (
    <div className="vstack">
      <h2 style={{ marginBottom: "0.25rem" }}>
        Edit Rx #{refill.prescription.id}
      </h2>
      <p style={{ color: "var(--text-light)", fontSize: "0.9rem", marginBottom: "1rem" }}>
        Current state: <strong>{priorState}</strong> — saving will send to{" "}
        <strong>{newStateLabel}</strong> for re-verification.
      </p>

      <div className="card" style={{ padding: "1.5rem", marginBottom: "1rem" }}>
        <div style={{ marginBottom: "1rem", fontSize: "0.95rem", color: "var(--text-light)" }}>
          <strong style={{ color: "var(--primary)", fontSize: "1.1rem" }}>{refill.drug.drug_name}</strong>
          {" — "}
          {refill.patient.first_name.toUpperCase()} {refill.patient.last_name.toUpperCase()}
        </div>

        <form onSubmit={handleSubmit}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem", marginBottom: "1rem" }}>
            <div>
              <label style={{ display: "block", fontWeight: "bold", marginBottom: "0.3rem" }}>
                Quantity
              </label>
              <input
                type="number"
                min="1"
                value={quantity}
                onChange={(e) => setQuantity(e.target.value)}
                required
                style={{ width: "100%", padding: "0.5rem", background: "var(--bg-light)", border: "1px solid var(--border)", borderRadius: "6px", color: "var(--text)" }}
              />
            </div>

            <div>
              <label style={{ display: "block", fontWeight: "bold", marginBottom: "0.3rem" }}>
                Days Supply
              </label>
              <input
                type="number"
                min="1"
                value={daysSupply}
                onChange={(e) => setDaysSupply(e.target.value)}
                required
                style={{ width: "100%", padding: "0.5rem", background: "var(--bg-light)", border: "1px solid var(--border)", borderRadius: "6px", color: "var(--text)" }}
              />
            </div>

            <div>
              <label style={{ display: "block", fontWeight: "bold", marginBottom: "0.3rem" }}>
                Priority
              </label>
              <select
                value={priority}
                onChange={(e) => setPriority(e.target.value)}
                style={{ width: "100%", padding: "0.5rem", background: "var(--bg-light)", border: "1px solid var(--border)", borderRadius: "6px", color: "var(--text)" }}
              >
                {PRIORITIES.map((p) => (
                  <option key={p} value={p}>{p.charAt(0).toUpperCase() + p.slice(1)}</option>
                ))}
              </select>
            </div>

            <div>
              <label style={{ display: "block", fontWeight: "bold", marginBottom: "0.3rem" }}>
                Due Date
              </label>
              <input
                type="date"
                value={dueDate}
                onChange={(e) => setDueDate(e.target.value)}
                required
                style={{ width: "100%", padding: "0.5rem", background: "var(--bg-light)", border: "1px solid var(--border)", borderRadius: "6px", color: "var(--text)" }}
              />
            </div>
          </div>

          <div style={{ marginBottom: "1rem" }}>
            <label style={{ display: "block", fontWeight: "bold", marginBottom: "0.3rem" }}>
              Instructions (Sig)
            </label>
            <textarea
              value={instructions}
              onChange={(e) => setInstructions(e.target.value)}
              rows={3}
              style={{ width: "100%", padding: "0.5rem", background: "var(--bg-light)", border: "1px solid var(--border)", borderRadius: "6px", color: "var(--text)", resize: "vertical", boxSizing: "border-box" }}
            />
          </div>

          <div style={{ marginBottom: "1.5rem" }}>
            <label style={{ display: "block", fontWeight: "bold", marginBottom: "0.3rem" }}>
              DAW Code
            </label>
            <select
              value={dawCode}
              onChange={(e) => setDawCode(parseInt(e.target.value, 10))}
              style={{ width: "100%", padding: "0.5rem", background: "var(--bg-light)", border: "1px solid var(--border)", borderRadius: "6px", color: "var(--text)" }}
            >
              {Object.entries(DAW_CODES).map(([code, desc]) => (
                <option key={code} value={code}>{code} — {desc}</option>
              ))}
            </select>
          </div>

          {error && (
            <div style={{ padding: "0.75rem", background: "rgba(239,71,111,0.1)", border: "1px solid var(--danger)", borderRadius: "6px", color: "var(--danger)", marginBottom: "1rem" }}>
              {error}
            </div>
          )}

          <div style={{ display: "flex", gap: "1rem", justifyContent: "flex-end" }}>
            <button
              type="button"
              className="btn"
              onClick={onBack}
              disabled={saving}
            >
              ← Cancel
            </button>
            <button
              type="submit"
              className="btn btn-primary"
              disabled={saving}
            >
              {saving ? "Saving..." : `Save & Send to ${newStateLabel}`}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
