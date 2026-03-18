import { useState } from "react";
import { searchPatients, fetchQueue, advanceRx } from "@/api";
import { useNotification } from "@/context/NotificationContext";
import Badge from "@/components/Badge";

function fmt(d) {
  return d ? new Date(d).toLocaleDateString() : "—";
}

function price(refill) {
  const amt = refill.copay_amount != null ? refill.copay_amount : refill.total_cost;
  return parseFloat(amt || 0);
}

function refillsRemaining(refill) {
  const remaining = refill.prescription.remaining_quantity - refill.quantity;
  if (remaining <= 0 || refill.quantity <= 0) return 0;
  return Math.floor(remaining / refill.quantity);
}

export default function RegisterView({ onBack }) {
  const { addNotification } = useNotification();
  const [lastName, setLastName] = useState("");
  const [firstName, setFirstName] = useState("");
  const [dob, setDob] = useState("");

  const [step, setStep] = useState("search"); // "search" | "candidates" | "checkout"
  const [candidates, setCandidates] = useState([]);
  const [patient, setPatient] = useState(null);
  const [allRefills, setAllRefills] = useState([]);
  const [selected, setSelected] = useState(new Set());
  const [selling, setSelling] = useState(false);
  const [error, setError] = useState("");

  const STATUS_ORDER = { READY: 0, QV2: 1, QP: 2, QV1: 3, QT: 4, HOLD: 5, SCHEDULED: 6, REJECTED: 7 };

  async function loadPatientRefills(pt) {
    setPatient(pt);
    setError("");
    try {
      const all = await fetchQueue(null);
      const mine = all
        .filter((r) => r.patient.id === pt.id && r.state !== "SOLD")
        .sort((a, b) => (STATUS_ORDER[a.state] ?? 99) - (STATUS_ORDER[b.state] ?? 99));
      setAllRefills(mine);
      setSelected(new Set(mine.filter((r) => r.state === "READY").map((r) => r.id)));
      setStep("checkout");
    } catch (e) {
      setError(e.message);
    }
  }

  async function handleSearch(e) {
    e.preventDefault();
    setError("");
    if (!lastName.trim()) return;
    const q = `${lastName.trim()},${firstName.trim()}`;
    try {
      let matches = await searchPatients(q);
      if (dob) {
        matches = matches.filter((p) => p.dob === dob);
      }
      if (matches.length === 0) {
        setError("No patients found matching that name and date of birth.");
        return;
      }
      if (matches.length === 1) {
        await loadPatientRefills(matches[0]);
      } else {
        setCandidates(matches);
        setStep("candidates");
      }
    } catch (e) {
      setError(e.message);
    }
  }

  async function handleSell() {
    if (selected.size === 0) return;
    if (!confirm(`Sell ${selected.size} prescription(s) to ${patient.last_name.toUpperCase()}, ${patient.first_name.toUpperCase()}?`)) return;
    setSelling(true);
    setError("");
    try {
      for (const id of selected) {
        await advanceRx(id, {});
      }
      const remaining = allRefills.filter((r) => !selected.has(r.id));
      setAllRefills(remaining);
      setSelected(new Set());
      addNotification("Sale complete!", "success");
    } catch (e) {
      setError(`Sale failed: ${e.message}`);
    } finally {
      setSelling(false);
    }
  }

  function toggleSelect(id, refill) {
    if (refill.state !== "READY") return;
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const readyRefills = allRefills.filter((r) => r.state === "READY");
  const total = readyRefills
    .filter((r) => selected.has(r.id))
    .reduce((sum, r) => sum + price(r), 0);

  // ── Step: search ──────────────────────────────────────────────────────────
  if (step === "search") {
    return (
      <div className="vstack" style={{ maxWidth: 480, margin: "0 auto", paddingTop: "2rem" }}>
        <h2 style={{ textAlign: "center", marginBottom: "2rem" }}>Register</h2>
        <div className="card vstack" style={{ gap: "1.2rem" }}>
          <div style={{ fontSize: "1rem", color: "var(--text-light)", textAlign: "center" }}>
            Enter patient information to look up prescriptions ready for pickup.
          </div>
          <form className="vstack" style={{ gap: "1rem" }} onSubmit={handleSearch}>
            <div className="hstack" style={{ gap: "0.75rem" }}>
              <div style={{ flex: 1, gap: "0.3rem" }} className="vstack">
                <label style={{ fontSize: "0.85rem", color: "var(--text-light)" }}>Last Name</label>
                <input
                  className="input"
                  placeholder="Last name"
                  value={lastName}
                  onChange={(e) => setLastName(e.target.value)}
                  autoFocus
                />
              </div>
              <div style={{ flex: 1, gap: "0.3rem" }} className="vstack">
                <label style={{ fontSize: "0.85rem", color: "var(--text-light)" }}>First Name</label>
                <input
                  className="input"
                  placeholder="First name"
                  value={firstName}
                  onChange={(e) => setFirstName(e.target.value)}
                />
              </div>
            </div>
            <div className="vstack" style={{ gap: "0.3rem" }}>
              <label style={{ fontSize: "0.85rem", color: "var(--text-light)" }}>Date of Birth</label>
              <input
                className="input"
                type="date"
                value={dob}
                onChange={(e) => setDob(e.target.value)}
              />
            </div>
            {error && <div style={{ color: "#ff7675", fontSize: "0.9rem" }}>{error}</div>}
            <button className="btn btn-primary" type="submit" style={{ marginTop: "0.5rem" }}>
              Look Up Patient
            </button>
          </form>
        </div>
        <div style={{ textAlign: "center", marginTop: "1rem" }}>
          <button className="btn btn-secondary" onClick={onBack}>Cancel</button>
        </div>
      </div>
    );
  }

  // ── Step: candidates ──────────────────────────────────────────────────────
  if (step === "candidates") {
    return (
      <div className="vstack" style={{ maxWidth: 520, margin: "0 auto", paddingTop: "2rem" }}>
        <h2 style={{ textAlign: "center", marginBottom: "1.5rem" }}>Select Patient</h2>
        <div className="card vstack" style={{ gap: "0.75rem" }}>
          {candidates.map((pt) => (
            <button
              key={pt.id}
              className="btn"
              style={{ justifyContent: "space-between", display: "flex", width: "100%" }}
              onClick={() => loadPatientRefills(pt)}
            >
              <span style={{ fontWeight: 600 }}>{pt.last_name.toUpperCase()}, {pt.first_name.toUpperCase()}</span>
              <span style={{ color: "var(--text-light)" }}>DOB: {new Date(pt.dob).toLocaleDateString()}</span>
            </button>
          ))}
        </div>
        {error && <div style={{ color: "#ff7675", fontSize: "0.9rem", marginTop: "0.5rem" }}>{error}</div>}
        <div style={{ textAlign: "center", marginTop: "1rem" }}>
          <button className="btn btn-secondary" onClick={() => { setStep("search"); setError(""); }}>Back</button>
        </div>
      </div>
    );
  }

  // ── Step: checkout ────────────────────────────────────────────────────────
  return (
    <div className="vstack">
      <div className="hstack" style={{ justifyContent: "space-between", alignItems: "center" }}>
        <h2 style={{ margin: 0 }}>Register — Checkout</h2>
        <button className="btn btn-secondary" onClick={() => { setStep("search"); setPatient(null); setAllRefills([]); setSelected(new Set()); setError(""); }}>
          New Patient
        </button>
      </div>

      <div className="card hstack" style={{ justifyContent: "space-between" }}>
        <div>
          <strong style={{ fontSize: "1.1rem" }}>{patient.last_name.toUpperCase()}, {patient.first_name.toUpperCase()}</strong>
        </div>
        <span style={{ color: "var(--text-light)" }}>
          DOB: {new Date(patient.dob).toLocaleDateString()}
        </span>
      </div>

      {allRefills.length === 0 ? (
        <p style={{ color: "var(--text-light)", textAlign: "center", fontSize: "1.2rem", marginTop: "2rem" }}>
          No active prescriptions found.
        </p>
      ) : (
        <>
          <table className="table">
            <thead>
              <tr>
                <th style={{ width: 36 }}></th>
                <th>Drug</th>
                <th>Qty Dispensed</th>
                <th>Days Supply</th>
                <th>Refills Left</th>
                <th>Last Updated</th>
                <th>Status</th>
                <th style={{ textAlign: "right" }}>Price</th>
              </tr>
            </thead>
            <tbody>
              {allRefills.map((r) => {
                const isReady = r.state === "READY";
                const checked = selected.has(r.id);
                const p = price(r);
                const rLeft = refillsRemaining(r);
                return (
                  <tr
                    key={r.id}
                    onClick={() => toggleSelect(r.id, r)}
                    style={{ cursor: isReady ? "pointer" : "default", opacity: isReady ? (checked ? 1 : 0.5) : 0.4 }}
                  >
                    <td>
                      {isReady ? (
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => toggleSelect(r.id, r)}
                          onClick={(e) => e.stopPropagation()}
                          style={{ cursor: "pointer", width: 16, height: 16 }}
                        />
                      ) : null}
                    </td>
                    <td><strong>{r.drug.drug_name}</strong></td>
                    <td>{r.quantity}</td>
                    <td>{r.days_supply}</td>
                    <td style={{ color: rLeft === 0 ? "#ff7675" : "inherit" }}>
                      {rLeft === 0 ? "Last fill" : rLeft}
                    </td>
                    <td>{fmt(r.completed_date)}</td>
                    <td><Badge state={r.state} /></td>
                    <td style={{ textAlign: "right", fontWeight: 600 }}>
                      {p > 0 ? (
                        <>
                          ${p.toFixed(2)}
                          {r.copay_amount != null && (
                            <div style={{ fontSize: "0.75rem", color: "var(--text-light)", fontWeight: 400 }}>
                              copay
                            </div>
                          )}
                        </>
                      ) : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          <div className="card hstack" style={{ justifyContent: "space-between", alignItems: "center", marginTop: "0.5rem" }}>
            <div style={{ fontSize: "0.9rem", color: "var(--text-light)" }}>
              {selected.size} of {readyRefills.length} ready prescription(s) selected
            </div>
            <div className="hstack" style={{ gap: "1.5rem", alignItems: "center" }}>
              <span style={{ fontSize: "1.4rem", fontWeight: 700 }}>
                Total: ${total.toFixed(2)}
              </span>
              <button
                className="btn btn-primary"
                style={{ fontSize: "1.05rem", padding: "10px 28px" }}
                disabled={selected.size === 0 || selling}
                onClick={handleSell}
              >
                {selling ? "Processing…" : "Sell"}
              </button>
            </div>
          </div>
        </>
      )}

      {error && <div style={{ color: "#ff7675", marginTop: "0.5rem" }}>{error}</div>}
    </div>
  );
}
