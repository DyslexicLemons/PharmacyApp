import React, { useContext, useEffect, useState } from "react";
import Badge from "@/components/Badge";
import { advanceRx, getStock, getRefill } from "@/api";
import { AuthContext } from "@/context/AuthContext";
import { useNotification } from "@/context/NotificationContext";
import { useQueryClient } from "@tanstack/react-query";
import type { Refill } from "@/types";
import { APPROVABLE_STATES, HOLDABLE_STATES, REJECTABLE_STATES, EDITABLE_STATES } from "@/types";

const DAW_CODES: Record<number, string> = {
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

interface RefillDetailViewProps {
  refillId: number;
  fromQueueState?: string;
  onBack?: () => void;
  onUpdate?: (updated: Refill) => void;
  onEdit?: () => void;
  keyCmd?: string | null;
  onKeyCmdHandled?: () => void;
}

export default function RefillDetailView({ refillId, fromQueueState, onBack, onUpdate, onEdit, keyCmd, onKeyCmdHandled }: RefillDetailViewProps) {
  const { token } = useContext(AuthContext);
  const { addNotification } = useNotification();
  const queryClient = useQueryClient();
  const [refill, setRefill] = useState<Refill | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showSellConfirm, setShowSellConfirm] = useState(false);
  const [scheduleNextFill, setScheduleNextFill] = useState(false);
  const [stockQty, setStockQty] = useState<number | null>(null);
  const [showHoldConfirm, setShowHoldConfirm] = useState(false);
  const [holdIsQV2, setHoldIsQV2] = useState(false);
  const [showRejectModal, setShowRejectModal] = useState(false);
  const [rejectReason, setRejectReason] = useState("");
  const [staleQueueMessage, setStaleQueueMessage] = useState<string | null>(null);

  useEffect(() => {
    fetchRefillDetails();
  }, [refillId]);

  useEffect(() => {
    if (!keyCmd || !refill) return;
    if (keyCmd === "approve" && APPROVABLE_STATES.includes(refill.state)) handleApprove();
    if (keyCmd === "hold" && HOLDABLE_STATES.includes(refill.state)) handleHold();
    onKeyCmdHandled?.();
  }, [keyCmd]);

  const fetchRefillDetails = async () => {
    if (!token) return;
    try {
      setLoading(true);
      const found = await getRefill(refillId, token, fromQueueState);
      if (fromQueueState && fromQueueState !== "ALL" && found.state !== fromQueueState) {
        setStaleQueueMessage(`This prescription is currently in ${found.state}, not ${fromQueueState}.`);
      } else {
        setRefill(found);
        setError("");
      }
    } catch (e: unknown) {
      const err = e as { status?: number; message?: string };
      if (err.status === 409) {
        setStaleQueueMessage(err.message ?? "This prescription has already been advanced to another queue.");
        queryClient.invalidateQueries({ queryKey: ["queue"] });
        queryClient.invalidateQueries({ queryKey: ["queue-summary"] });
      } else {
        setError((e as Error).message);
      }
    } finally {
      setLoading(false);
    }
  };

  const handleApprove = async () => {
    if (!refill) return;
    if (refill.state === "READY") {
      if (!token) return;
      try {
        const stocks = await getStock(token);
        const items = Array.isArray(stocks) ? stocks : (stocks.items ?? []);
        const entry = items.find((s: { drug_id: number; quantity: number }) => s.drug_id === refill.drug_id);
        setStockQty(entry ? entry.quantity : 0);
        setScheduleNextFill(false);
        setShowSellConfirm(true);
      } catch (e) {
        addNotification(`Error fetching stock: ${(e as Error).message}`, "error");
      }
      return;
    }
    if (!token) return;
    try {
      const updated = await advanceRx(refillId, {}, token);
      queryClient.invalidateQueries({ queryKey: ["queue"] });
      queryClient.invalidateQueries({ queryKey: ["queue-summary"] });
      addNotification(`RX# ${updated.prescription.id} advanced to ${updated.state}`, "success");
      if (onUpdate) onUpdate(updated);
      if (onBack) onBack();
    } catch (e) {
      addNotification(`Error: ${(e as Error).message}`, "error");
    }
  };

  const handleConfirmSell = async () => {
    if (!token) return;
    try {
      const updated = await advanceRx(refillId, { schedule_next_fill: scheduleNextFill }, token);
      queryClient.invalidateQueries({ queryKey: ["queue"] });
      queryClient.invalidateQueries({ queryKey: ["queue-summary"] });
      addNotification(`Rx #${updated.prescription.id} marked as SOLD${scheduleNextFill ? " — next fill scheduled" : ""}`, "success");
      if (onUpdate) onUpdate(updated);
      if (onBack) onBack();
    } catch (e) {
      addNotification(`Error: ${(e as Error).message}`, "error");
    }
  };

  const handleReject = () => {
    setRejectReason("");
    setShowRejectModal(true);
  };

  const handleConfirmReject = async () => {
    if (!rejectReason.trim()) return;
    if (!token) return;
    setShowRejectModal(false);
    try {
      const updated = await advanceRx(refillId, {
        action: "reject",
        rejection_reason: rejectReason.trim(),
      }, token);
      queryClient.invalidateQueries({ queryKey: ["queue"] });
      queryClient.invalidateQueries({ queryKey: ["queue-summary"] });
      addNotification(`Rx returned to triage: ${rejectReason.trim()}`, "warning");
      if (onUpdate) onUpdate(updated);
      if (onBack) onBack();
    } catch (e) {
      addNotification(`Error: ${(e as Error).message}`, "error");
    }
  };

  const handleHold = () => {
    if (!refill) return;
    setHoldIsQV2(refill.state === "QV2");
    setShowHoldConfirm(true);
  };

  const handleConfirmHold = async () => {
    if (!token) return;
    setShowHoldConfirm(false);
    try {
      const updated = await advanceRx(refillId, { action: "hold" }, token);
      queryClient.invalidateQueries({ queryKey: ["queue"] });
      queryClient.invalidateQueries({ queryKey: ["queue-summary"] });
      if (holdIsQV2) {
        addNotification("Prescription placed on HOLD. This script has been filled — please return the medication to stock.", "warning");
      } else {
        addNotification("Prescription moved to HOLD", "info");
      }
      if (onUpdate) onUpdate(updated);
      if (onBack) onBack();
    } catch (e) {
      addNotification(`Error: ${(e as Error).message}`, "error");
    }
  };

  const isStaleQueue =
    staleQueueMessage !== null ||
    (refill !== null && fromQueueState && fromQueueState !== "ALL" && refill.state !== fromQueueState);

  if (loading) return <div className="vstack"><p>Loading...</p></div>;
  if (error) return <div className="vstack"><p style={{ color: "var(--danger)" }}>{error}</p></div>;
  if (isStaleQueue) {
    const staleDetail = staleQueueMessage
      ?? (refill ? `This prescription is currently in ${refill.state}, not ${fromQueueState}.` : "");
    return (
      <div style={{
        position: "fixed", inset: 0, background: "rgba(0,0,0,0.55)",
        display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000,
      }}>
        <div className="card vstack" style={{ maxWidth: "420px", width: "92%", gap: "1rem", padding: "1.5rem", border: "2px solid var(--warning, #f59e0b)" }}>
          <h3 style={{ margin: 0, color: "var(--warning, #f59e0b)" }}>Rx #{refillId} — Already Advanced</h3>
          <p style={{ margin: 0, fontSize: "0.95rem" }}>
            This prescription has been moved to another queue by another user and can no longer be accessed from here.
          </p>
          {staleDetail && (
            <p style={{ margin: 0, fontSize: "0.85rem", color: "var(--text-light)" }}>{staleDetail}</p>
          )}
          <div style={{ display: "flex", justifyContent: "flex-end" }}>
            <button className="btn btn-secondary" onClick={onBack}>← Back to Queue</button>
          </div>
        </div>
      </div>
    );
  }
  if (!refill) return <div className="vstack"><p>Refill not found</p></div>;

  const canApprove = APPROVABLE_STATES.includes(refill.state);
  const canReject = REJECTABLE_STATES.includes(refill.state);
  const canHold = HOLDABLE_STATES.includes(refill.state);
  const canEdit = EDITABLE_STATES.includes(refill.state);

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

      {refill.state === "QT" && (
        <div style={{ padding: "1rem", background: "rgba(251, 191, 36, 0.12)", border: "2px solid #fbbf24", borderRadius: "8px", marginBottom: "1rem" }}>
          <strong style={{ color: "#92620a" }}>
            {refill.triage_reason?.startsWith("Pharmacist rejected:") ? "Returned by Pharmacist" : "Triage Required"}
          </strong>
          <div style={{ marginTop: "0.5rem" }}>
            <strong>Reason:</strong> {refill.triage_reason ?? "no reason recorded"}
          </div>
          {refill.rejected_by && refill.triage_reason?.startsWith("Pharmacist rejected:") && (
            <div style={{ marginTop: "0.25rem", fontSize: "0.9rem", color: "var(--text-light)" }}>
              Returned by: {refill.rejected_by} on {refill.rejection_date}
            </div>
          )}
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
          <span style={{ color: "var(--text-light)", fontSize: "0.9rem" }}>DOB: {(refill.patient as unknown as Record<string, string>).dob}</span>
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
                <span>{refill.prescription.daw_code ?? "—"} — {refill.prescription.daw_code != null ? (DAW_CODES[refill.prescription.daw_code] ?? "Unknown") : "—"}</span>

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

      {showRejectModal && (
        <div style={{
          position: "fixed", inset: 0, background: "rgba(0,0,0,0.55)",
          display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000,
        }}>
          <div className="card vstack" style={{ maxWidth: "440px", width: "92%", gap: "1rem", padding: "1.5rem", border: "2px solid var(--danger)" }}>
            <h3 style={{ margin: 0, color: "var(--danger)" }}>✕ Reject</h3>
            <p style={{ margin: 0, fontSize: "0.95rem" }}>
              This prescription will be returned to the <strong>QT queue</strong> for the technician to review. A rejection reason is required.
            </p>
            <div>
              <label style={{ display: "block", fontWeight: 600, marginBottom: "0.4rem", fontSize: "0.9rem" }}>
                Rejection reason <span style={{ color: "var(--danger)" }}>*</span>
              </label>
              <textarea
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
                rows={3}
                maxLength={500}
                placeholder="Describe the reason for rejection..."
                style={{
                  width: "100%", boxSizing: "border-box", resize: "vertical",
                  padding: "0.5rem 0.75rem", borderRadius: "6px",
                  border: "1px solid var(--border)", fontSize: "0.95rem",
                  background: "var(--bg-light)", color: "var(--text)",
                }}
                autoFocus
              />
            </div>
            <div style={{ display: "flex", gap: "0.75rem", justifyContent: "flex-end" }}>
              <button className="btn btn-secondary" onClick={() => setShowRejectModal(false)}>Cancel</button>
              <button
                className="btn btn-danger"
                onClick={handleConfirmReject}
                disabled={!rejectReason.trim()}
              >
                Reject
              </button>
            </div>
          </div>
        </div>
      )}

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
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setScheduleNextFill(e.target.checked)}
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
            style={{ minWidth: "160px" }}
          >
            ✕ Reject
          </button>
        )}
      </div>
    </div>
  );
}
