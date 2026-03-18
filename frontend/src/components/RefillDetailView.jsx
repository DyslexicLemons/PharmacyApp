import { useContext, useEffect, useState } from "react";
import Badge from "@/components/Badge";
import { advanceRx, getStock, getRefill } from "@/api";
import { AuthContext } from "@/context/AuthContext";
import { useNotification } from "@/context/NotificationContext";

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

export default function RefillDetailView({ refillId, onBack, onUpdate, onEdit, keyCmd, onKeyCmdHandled }) {
  const { token } = useContext(AuthContext);
  const { addNotification } = useNotification();
  const [refill, setRefill] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showSellConfirm, setShowSellConfirm] = useState(false);
  const [scheduleNextFill, setScheduleNextFill] = useState(false);
  const [stockQty, setStockQty] = useState(null);
  const [showHoldConfirm, setShowHoldConfirm] = useState(false);
  const [holdIsQV2, setHoldIsQV2] = useState(false);

  useEffect(() => {
    fetchRefillDetails();
  }, [refillId]);

  useEffect(() => {
    if (!keyCmd || !refill) return;
    const approveStates = ["QT", "QV1", "QP", "QV2", "READY", "HOLD", "SCHEDULED"];
    const holdStates = ["QT", "QV1", "QP", "QV2"];
    if (keyCmd === "approve" && approveStates.includes(refill.state)) handleApprove();
    if (keyCmd === "hold" && holdStates.includes(refill.state)) handleHold();
    onKeyCmdHandled?.();
  }, [keyCmd]);

  const fetchRefillDetails = async () => {
    try {
      setLoading(true);
      const found = await getRefill(refillId, token);
      setRefill(found);
      setError("");
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleApprove = async () => {
    if (refill.state === "READY") {
      try {
        const stocks = await getStock(token);
        const items = Array.isArray(stocks) ? stocks : (stocks.items ?? []);
        const entry = items.find(s => s.drug_id === refill.drug_id);
        setStockQty(entry ? entry.quantity : 0);
        setScheduleNextFill(false);
        setShowSellConfirm(true);
      } catch (e) {
        addNotification(`Error fetching stock: ${e.message}`, "error");
      }
      return;
    }
    try {
      const updated = await advanceRx(refillId, {}, token);
      addNotification(`RX# ${updated.prescription.id} advanced to ${updated.state}`, "success");
      if (onUpdate) onUpdate(updated);
      if (onBack) onBack();
    } catch (e) {
      addNotification(`Error: ${e.message}`, "error");
    }
  };

  const handleConfirmSell = async () => {
    try {
      const updated = await advanceRx(refillId, { schedule_next_fill: scheduleNextFill }, token);
      addNotification(`Rx #${updated.prescription.id} marked as SOLD${scheduleNextFill ? " — next fill scheduled" : ""}`, "success");
      if (onUpdate) onUpdate(updated);
      if (onBack) onBack();
    } catch (e) {
      addNotification(`Error: ${e.message}`, "error");
    }
  };

  const handleReject = async () => {
    const reason = prompt("Rejection reason:");
    if (!reason) return;
    const rejectedBy = prompt("Rejected by (name):");
    if (!rejectedBy) return;

    try {
      const updated = await advanceRx(refillId, {
        action: "reject",
        rejection_reason: reason,
        rejected_by: rejectedBy
      }, token);
      addNotification("Prescription rejected successfully", "info");
      if (onUpdate) onUpdate(updated);
      if (onBack) onBack();
    } catch (e) {
      addNotification(`Error: ${e.message}`, "error");
    }
  };

  const handleHold = () => {
    setHoldIsQV2(refill.state === "QV2");
    setShowHoldConfirm(true);
  };

  const handleConfirmHold = async () => {
    setShowHoldConfirm(false);
    try {
      const updated = await advanceRx(refillId, { action: "hold" }, token);
      if (holdIsQV2) {
        addNotification("Prescription placed on HOLD. This script has been filled — please return the medication to stock.", "warning");
      } else {
        addNotification("Prescription moved to HOLD", "info");
      }
      if (onUpdate) onUpdate(updated);
      if (onBack) onBack();
    } catch (e) {
      addNotification(`Error: ${e.message}`, "error");
    }
  };

  if (loading) return <div className="vstack"><p>Loading...</p></div>;
  if (error) return <div className="vstack"><p style={{ color: "var(--danger)" }}>{error}</p></div>;
  if (!refill) return <div className="vstack"><p>Refill not found</p></div>;

  const canApprove = ["QT", "QV1", "QP", "QV2", "READY", "HOLD", "SCHEDULED"].includes(refill.state);
  const canReject = ["QV1", "HOLD"].includes(refill.state);
  const canHold = ["QT", "QV1", "QP", "QV2"].includes(refill.state);
  const canEdit = ["QT", "QP", "HOLD"].includes(refill.state);

  return (
    <div className="vstack">
      <h2 style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
        <span>Rx #: {refill.prescription.id}</span>
        <span style={{ fontSize: "1.6rem" }}><Badge state={refill.state} /></span>
      </h2>

      {/* Alerts for READY bin number and REJECTED status */}
      {refill.state === "READY" && refill.bin_number && (
        <div style={{ padding: "1rem", background: "var(--success)", color: "white", borderRadius: "8px", marginBottom: "1rem" }}>
          <strong style={{ fontSize: "1.2rem" }}>Bin Number: {refill.bin_number}</strong>
        </div>
      )}

      {refill.state === "REJECTED" && (
        <div style={{ padding: "1rem", background: "rgba(239, 71, 111, 0.1)", border: "2px solid var(--danger)", borderRadius: "8px", marginBottom: "1rem" }}>
          <strong>Rejected</strong>
          <div style={{ marginTop: "0.5rem" }}>
            <strong>By:</strong> {refill.rejected_by}
          </div>
          <div style={{ marginTop: "0.25rem" }}>
            <strong>Reason:</strong> {refill.rejection_reason}
          </div>
          <div style={{ marginTop: "0.25rem", fontSize: "0.9rem", color: "var(--text-light)" }}>
            Date: {refill.rejection_date}
          </div>
        </div>
      )}

      <div className="card" style={{ padding: "1.5rem", marginBottom: "1rem" }}>
        {/* Patient Information at the top */}
        <div style={{ marginBottom: "0.75rem", paddingBottom: "0.6rem", borderBottom: "2px solid var(--bg-light)", display: "flex", gap: "2rem", alignItems: "baseline", flexWrap: "wrap" }}>
          <h3 style={{ margin: 0, fontSize: "1rem", flexShrink: 0 }}>Patient</h3>
          <span><strong>{refill.patient.first_name.toUpperCase()} {refill.patient.last_name.toUpperCase()}</strong></span>
          <span style={{ color: "var(--text-light)", fontSize: "0.9rem" }}>DOB: {refill.patient.dob}</span>
          <span style={{ color: "var(--text-light)", fontSize: "0.9rem" }}>{refill.patient.address}</span>
        </div>

        {/* Prescription Details */}
        <div style={{ marginBottom: "1.25rem", paddingBottom: "1rem", borderBottom: "2px solid var(--bg-light)" }}>
          <h3 style={{ margin: "0 0 0.75rem 0", fontSize: "1.1rem" }}>Prescription</h3>
          <div style={{ display: "flex", gap: "1.5rem", alignItems: "flex-start" }}>
            {/* Left: prescription fields */}
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: "0.4rem 1.5rem", fontSize: "0.95rem" }}>
                <strong>Rx #:</strong>
                <span>{refill.prescription.id}</span>

                <strong>Date Created:</strong>
                <span>{refill.prescription.date_received ? new Date(refill.prescription.date_received).toLocaleDateString() : "—"}</span>

                <strong>Expiration:</strong>
                <span>{refill.prescription.expiration_date ? new Date(refill.prescription.expiration_date).toLocaleDateString() : "—"}</span>

                <strong>DAW Code:</strong>
                <span>{refill.prescription.daw_code} — {DAW_CODES[refill.prescription.daw_code] ?? "Unknown"}</span>

                <strong>Orig. Qty:</strong>
                <span>{refill.prescription.original_quantity}</span>

                <strong>Remaining:</strong>
                <span>{refill.prescription.remaining_quantity}</span>

                <strong>Source:</strong>
                <span>{refill.source}</span>
              </div>
              {refill.prescription.instructions && (
                <div style={{ marginTop: "0.75rem", padding: "0.5rem 0.75rem", background: "var(--bg-light)", borderRadius: "6px", fontSize: "0.9rem" }}>
                  <strong>Instructions:</strong>
                  <div style={{ marginTop: "0.25rem" }}>{refill.prescription.instructions}</div>
                </div>
              )}
            </div>

            {/* Middle: prescriber info */}
            {refill.prescription.prescriber && (
              <div style={{ flexShrink: 0, width: "200px" }}>
                <div style={{ fontSize: "0.85rem", fontWeight: 600, color: "var(--text-light)", marginBottom: "0.4rem", textTransform: "uppercase", letterSpacing: "0.04em" }}>Prescriber</div>
                <div style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: "0.4rem 0.75rem", fontSize: "0.9rem" }}>
                  <strong>Name:</strong>
                  <span>Dr. {refill.prescription.prescriber.first_name} {refill.prescription.prescriber.last_name}</span>

                  <strong>NPI:</strong>
                  <span>{refill.prescription.prescriber.npi}</span>

                  <strong>Phone:</strong>
                  <span>{refill.prescription.prescriber.phone_number}</span>

                  <strong>Address:</strong>
                  <span>{refill.prescription.prescriber.address}</span>
                </div>
              </div>
            )}

            {/* Right: prescription image */}
            <div style={{ flexShrink: 0, width: "280px" }}>
              <div style={{ fontSize: "0.85rem", fontWeight: 600, color: "var(--text-light)", marginBottom: "0.4rem", textTransform: "uppercase", letterSpacing: "0.04em" }}>Image</div>
              {refill.prescription.picture ? (
                <img
                  src={refill.prescription.picture}
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

        {/* Refill Details */}
        <div style={{ marginBottom: "1.25rem", paddingBottom: "1rem", borderBottom: "2px solid var(--bg-light)" }}>
          <h3 style={{ margin: "0 0 0.75rem 0", fontSize: "1.1rem" }}>This Refill</h3>
          <div style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: "0.4rem 1.5rem", fontSize: "0.95rem" }}>
            <strong>Fill Qty:</strong>
            <span>{refill.quantity}</span>

            <strong>Days Supply:</strong>
            <span>{refill.days_supply}</span>

            <strong>Pickup Cost:</strong>
            <span>${Number(refill.total_cost).toFixed(2)}</span>
          </div>
        </div>

        {/* Drug Information */}
        <div style={{ marginBottom: "1.5rem" }}>
          <h3 style={{ margin: "0 0 0.75rem 0", fontSize: "1.1rem" }}>Drug Information</h3>
          <div style={{ fontSize: "1.3rem", fontWeight: "bold", marginBottom: "0.5rem", color: "var(--primary)" }}>
            {refill.drug.drug_name}
          </div>
          {refill.drug.drug_class === 2 && (
            <div style={{
              display: "inline-block",
              padding: "0.2rem 0.6rem",
              background: "rgba(239, 71, 111, 0.15)",
              border: "1px solid var(--danger)",
              borderRadius: "4px",
              color: "var(--danger)",
              fontWeight: "bold",
              fontSize: "0.85rem",
              marginBottom: "0.75rem"
            }}>
              C-II Controlled Substance
            </div>
          )}
          <div style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: "0.25rem 1rem", marginBottom: "1rem" }}>
            <strong>NDC:</strong>
            <span style={{ fontFamily: "monospace" }}>{refill.drug.ndc ?? "—"}</span>
            <strong>Manufacturer:</strong>
            <span>{refill.drug.manufacturer}</span>
          </div>

          {refill.drug.description && (
            <div style={{
              padding: "0.75rem",
              background: "var(--bg-light)",
              borderRadius: "6px",
              border: "1px solid var(--primary)",
              fontSize: "0.9rem",
              marginBottom: "0.75rem"
            }}>
              <strong>Physical Description:</strong>
              <div style={{ marginTop: "0.25rem" }}>{refill.drug.description}</div>
            </div>
          )}

          {refill.drug.niosh && (
            <div style={{
              padding: "0.75rem",
              background: "rgba(239, 71, 111, 0.1)",
              border: "2px solid var(--danger)",
              borderRadius: "6px",
              fontWeight: "bold",
              fontSize: "0.9rem"
            }}>
              ⚠️ NIOSH HAZARDOUS DRUG - Special handling required
            </div>
          )}
        </div>

      </div>

      {showHoldConfirm && (
        <div style={{
          position: "fixed", inset: 0, background: "rgba(0,0,0,0.55)",
          display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000,
        }}>
          <div className="card vstack" style={{ maxWidth: "420px", width: "92%", gap: "1rem", padding: "1.5rem", border: "2px solid var(--warning, #f59e0b)" }}>
            <h3 style={{ margin: 0, color: "var(--warning, #f59e0b)" }}>⏸ Place on Hold</h3>
            <p style={{ margin: 0, fontSize: "0.95rem" }}>
              {holdIsQV2
                ? <>This script has already been filled. Placing it on hold means you will need to <strong>return the medication to stock</strong>. Proceed?</>
                : "Move this prescription to HOLD?"}
            </p>
            <div style={{ display: "flex", gap: "0.75rem", justifyContent: "flex-end" }}>
              <button className="btn btn-secondary" onClick={() => setShowHoldConfirm(false)}>Cancel</button>
              <button
                className="btn btn-warning"
                onClick={handleConfirmHold}
              >
                Confirm Hold
              </button>
            </div>
          </div>
        </div>
      )}

      {showSellConfirm && (() => {
        const nextFillDate = new Date();
        nextFillDate.setDate(nextFillDate.getDate() + refill.days_supply);
        const insufficient = stockQty !== null && stockQty < refill.quantity;
        return (
          <div style={{
            position: "fixed", top: 0, left: 0, right: 0, bottom: 0,
            background: "rgba(0,0,0,0.55)", display: "flex",
            alignItems: "center", justifyContent: "center", zIndex: 1000
          }}>
            <div className="card" style={{ padding: "2rem", maxWidth: "480px", width: "90%" }}>
              <h3 style={{ marginTop: 0 }}>Confirm Sale</h3>
              <p style={{ marginBottom: "1.25rem" }}>
                Mark <strong>Rx #{refill.prescription.id}</strong> —{" "}
                <strong>{refill.drug.drug_name}</strong> for{" "}
                <strong>{refill.patient.first_name.toUpperCase()} {refill.patient.last_name.toUpperCase()}</strong> as sold?
              </p>

              <label style={{ display: "flex", alignItems: "center", gap: "0.6rem", fontSize: "1rem", cursor: "pointer" }}>
                <input
                  type="checkbox"
                  checked={scheduleNextFill}
                  onChange={e => setScheduleNextFill(e.target.checked)}
                  style={{ width: "1.1rem", height: "1.1rem" }}
                />
                Schedule next fill
              </label>

              {scheduleNextFill && (
                <div style={{
                  marginTop: "1rem", padding: "0.85rem 1rem",
                  background: "var(--bg-light)", borderRadius: "8px",
                  border: "1px solid var(--border)", fontSize: "0.95rem"
                }}>
                  <div style={{ marginBottom: "0.4rem" }}>
                    <strong>Next fill date:</strong>{" "}
                    {nextFillDate.toLocaleDateString()}{" "}
                    <span style={{ color: "var(--text-light)" }}>
                      ({refill.days_supply} days from today)
                    </span>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                    <strong>Stock:</strong>{" "}
                    {stockQty ?? "?"} available &nbsp;|&nbsp; {refill.quantity} needed
                    {insufficient && (
                      <span style={{
                        color: "var(--danger)", fontWeight: "bold",
                        background: "rgba(239,71,111,0.1)", padding: "0.15rem 0.5rem",
                        borderRadius: "4px"
                      }}>
                        ⚠ Insufficient stock
                      </span>
                    )}
                  </div>
                </div>
              )}

              <div style={{ display: "flex", gap: "1rem", justifyContent: "flex-end", marginTop: "1.75rem" }}>
                <button className="btn" onClick={() => setShowSellConfirm(false)}>
                  Cancel
                </button>
                <button className="btn btn-success" onClick={handleConfirmSell}>
                  Confirm Sale
                </button>
              </div>
            </div>
          </div>
        );
      })()}

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
        <button
          className="btn"
          onClick={onBack}
          style={{ minWidth: "120px" }}
        >
          ← Back
        </button>

        {canApprove && (
          <button
            className="btn btn-success"
            onClick={handleApprove}
            style={{ minWidth: "180px" }}
          >
            ✓ Approve & Advance [a]
          </button>
        )}

        {canHold && (
          <button
            className="btn btn-warning"
            onClick={handleHold}
            style={{ minWidth: "120px" }}
          >
            ⏸ Hold [h]
          </button>
        )}

        {canEdit && onEdit && (
          <button
            className="btn btn-secondary"
            onClick={onEdit}
            style={{ minWidth: "120px" }}
          >
            ✎ Edit [e]
          </button>
        )}

        {canReject && (
          <button
            className="btn btn-danger"
            onClick={handleReject}
            style={{ minWidth: "120px" }}
          >
            ✗ Reject
          </button>
        )}
      </div>
    </div>
  );
}
