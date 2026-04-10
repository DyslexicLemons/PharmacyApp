import { useContext, useEffect, useRef, useState } from "react";
import { AuthContext } from "@/context/AuthContext";
import { useNotification } from "@/context/NotificationContext";
import { rtsLookup, rtsLookupByRx, processRTS } from "@/api";
import type { RTSLookup } from "@/types";

interface RTSViewProps {
  initialRefillId?: number;
  onBack: () => void;
}

export default function RTSView({ initialRefillId, onBack }: RTSViewProps) {
  const { token } = useContext(AuthContext);
  const { addNotification } = useNotification();
  const [inputId, setInputId] = useState(initialRefillId ? String(initialRefillId) : "");

  const [lookup, setLookup] = useState<RTSLookup | null>(null);
  const [lookupError, setLookupError] = useState("");
  const [processing, setProcessing] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // If we were launched with a specific refill ID, look it up immediately
  useEffect(() => {
    if (initialRefillId && token) {
      fetchLookup(initialRefillId);
    } else {
      inputRef.current?.focus();
    }
  }, []);

  function fetchLookup(id: number) {
    setLookupError("");
    setLookup(null);
    rtsLookup(id, token!)
      .then(setLookup)
      .catch((e: Error) => setLookupError(e.message));
  }

  function fetchLookupByRx(id: number) {
    setLookupError("");
    setLookup(null);
    rtsLookupByRx(id, token!)
      .then(setLookup)
      .catch((e: Error) => setLookupError(e.message));
  }

  function handleLookupSubmit(e: React.FormEvent) {
    e.preventDefault();
    const id = parseInt(inputId.trim(), 10);
    if (isNaN(id) || id <= 0) {
      setLookupError("Please enter a valid Rx number.");
      return;
    }
    fetchLookupByRx(id);
  }

  function handleConfirm() {
    if (!lookup) return;
    setProcessing(true);
    processRTS(lookup.refill_id, token!)
      .then(() => {
        addNotification(`Rx #${inputId} (${lookup.drug_name}) returned to stock and placed on hold.`, "success");
        setLookup(null);
        setInputId("");
        setLookupError("");
      })
      .catch((e: Error) => setLookupError(e.message))
      .finally(() => setProcessing(false));
  }

  return (
    <div className="vstack" style={{ gap: "1.5rem", maxWidth: 520 }}>
      <h2>Return to Stock (RTS)</h2>
      <p style={{ color: "var(--text-light)", margin: 0 }}>
        Enter the Rx number to return a READY prescription to stock inventory.
      </p>

      {/* Rx ID lookup form */}
      {!lookup && (
        <div className="vstack" style={{ gap: "0.75rem" }}>
          <form onSubmit={handleLookupSubmit} style={{ display: "flex", gap: "0.75rem", alignItems: "flex-end" }}>
            <div className="vstack" style={{ gap: "0.25rem", flex: 1 }}>
              <label style={{ fontSize: "0.85rem", color: "var(--text-light)" }}>
                Rx Number (Prescription ID)
              </label>
              <input
                ref={inputRef}
                className="input"
                type="number"
                min={1}
                value={inputId}
                onChange={(e) => setInputId(e.target.value)}
                placeholder="e.g. 1701234"
                style={{ fontFamily: "monospace", fontSize: "1.1rem" }}
              />
            </div>
            <button className="btn btn-primary" type="submit">
              Look Up
            </button>
          </form>
        </div>
      )}

      {lookupError && (
        <div style={{ color: "var(--danger, #ff7675)", fontSize: "0.9rem" }}>{lookupError}</div>
      )}

      {/* Confirmation panel */}
      {lookup && (
        <div className="vstack" style={{ gap: "1rem" }}>
          <div
            className="card"
            style={{
              padding: "1.25rem",
              background: "rgba(255, 190, 11, 0.06)",
              border: "1px solid rgba(255, 190, 11, 0.3)",
            }}
          >
            <h3 style={{ margin: "0 0 1rem", fontSize: "1rem", color: "var(--text-light)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
              Confirm Return to Stock
            </h3>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <tbody>
                <tr>
                  <td style={{ color: "var(--text-light)", paddingBottom: "0.4rem", width: "40%" }}>Rx #</td>
                  <td style={{ fontWeight: 600, fontFamily: "monospace" }}>{lookup.refill_id}</td>
                </tr>
                <tr>
                  <td style={{ color: "var(--text-light)", paddingBottom: "0.4rem" }}>Drug</td>
                  <td style={{ fontWeight: 600 }}>{lookup.drug_name}</td>
                </tr>
                {lookup.ndc && (
                  <tr>
                    <td style={{ color: "var(--text-light)", paddingBottom: "0.4rem" }}>NDC</td>
                    <td style={{ fontFamily: "monospace", fontSize: "0.9rem" }}>{lookup.ndc}</td>
                  </tr>
                )}
                <tr>
                  <td style={{ color: "var(--text-light)", paddingBottom: "0.4rem" }}>Quantity</td>
                  <td style={{ fontWeight: 700, fontSize: "1.1rem", color: "var(--primary)" }}>
                    {lookup.quantity} units
                  </td>
                </tr>
                <tr>
                  <td style={{ color: "var(--text-light)", paddingBottom: "0.4rem" }}>Patient</td>
                  <td>{lookup.patient_name}</td>
                </tr>
                {lookup.bin_number != null && (
                  <tr>
                    <td style={{ color: "var(--text-light)", paddingBottom: "0.4rem" }}>Bin #</td>
                    <td style={{ fontFamily: "monospace" }}>{lookup.bin_number}</td>
                  </tr>
                )}
                {lookup.completed_date && (
                  <tr>
                    <td style={{ color: "var(--text-light)", paddingBottom: "0.4rem" }}>Filled Date</td>
                    <td>{lookup.completed_date}</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <p style={{ color: "var(--text-light)", fontSize: "0.9rem", margin: 0 }}>
            Confirming will add <strong>{lookup.quantity} units</strong> of <strong>{lookup.drug_name}</strong> back
            to stock and restore the prescription quantity.
          </p>

          <div style={{ display: "flex", gap: "0.75rem" }}>
            <button
              className="btn btn-primary"
              onClick={handleConfirm}
              disabled={processing}
              style={{ minWidth: 140 }}
            >
              {processing ? "Processing…" : "Confirm RTS"}
            </button>
            <button
              className="btn btn-secondary"
              onClick={() => { setLookup(null); setInputId(""); setLookupError(""); }}
              disabled={processing}
            >
              Clear
            </button>
            <button className="btn btn-secondary" onClick={onBack} disabled={processing}>
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
