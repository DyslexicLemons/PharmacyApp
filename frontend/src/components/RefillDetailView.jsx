import React, { useEffect, useState } from "react";
import Badge from "@/components/Badge";
import { advanceRx } from "@/api";

const API = import.meta.env.VITE_API_BASE || 'http://localhost:8000';

export default function RefillDetailView({ refillId, onBack, onUpdate }) {
  const [refill, setRefill] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchRefillDetails();
  }, [refillId]);

  const fetchRefillDetails = async () => {
    try {
      setLoading(true);
      // Fetch all refills (no state filter) to get complete data
      const res = await fetch(`${API}/refills`);
      if (!res.ok) {
        const errorText = await res.text();
        throw new Error(`Failed to fetch refills: ${errorText}`);
      }
      const data = await res.json();
      const found = data.find(r => r.id === refillId);
      if (!found) throw new Error("Refill not found");
      setRefill(found);
      setError("");
    } catch (e) {
      console.error("Error fetching refill details:", e);
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleApprove = async () => {
    try {
      const updated = await advanceRx(refillId, {});
      alert(`Prescription advanced to ${updated.state}`);
      if (onUpdate) onUpdate(updated);
      if (onBack) onBack();
    } catch (e) {
      alert(`Error: ${e.message}`);
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
      });
      alert("Prescription rejected successfully");
      if (onUpdate) onUpdate(updated);
      if (onBack) onBack();
    } catch (e) {
      alert(`Error: ${e.message}`);
    }
  };

  const handleHold = async () => {
    const confirm = window.confirm("Move this prescription to HOLD?");
    if (!confirm) return;

    try {
      const updated = await advanceRx(refillId, { action: "hold" });
      alert("Prescription moved to HOLD");
      if (onUpdate) onUpdate(updated);
      if (onBack) onBack();
    } catch (e) {
      alert(`Error: ${e.message}`);
    }
  };

  if (loading) return <div className="vstack"><p>Loading...</p></div>;
  if (error) return <div className="vstack"><p style={{ color: "var(--danger)" }}>{error}</p></div>;
  if (!refill) return <div className="vstack"><p>Refill not found</p></div>;

  const canApprove = ["QT", "QV1", "QP", "QV2", "READY", "HOLD"].includes(refill.state);
  const canReject = ["QV1", "HOLD"].includes(refill.state);
  const canHold = refill.state === "QV1";

  return (
    <div className="vstack">
      <h2 style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
        <span>Refill Details - ID #{refill.id}</span>
        <Badge state={refill.state} />
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
        <div style={{ marginBottom: "1.5rem", paddingBottom: "1rem", borderBottom: "2px solid var(--bg-light)" }}>
          <h3 style={{ margin: "0 0 0.75rem 0", fontSize: "1.1rem" }}>Patient</h3>
          <div style={{ display: "grid", gridTemplateColumns: "auto auto 1fr", gap: "0.5rem 1.5rem", alignItems: "baseline" }}>
            <strong>Name:</strong>
            <span>{refill.patient.first_name} {refill.patient.last_name}</span>
            <div></div>

            <strong>DOB:</strong>
            <span>{refill.patient.dob}</span>
            <div></div>

            <strong>Address:</strong>
            <span>{refill.patient.address}</span>
            <div></div>
          </div>
        </div>

        {/* Main content area with Drug info and Prescription details */}
        <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: "2rem", marginBottom: "1.5rem" }}>
          {/* Left: Drug Information */}
          <div>
            <h3 style={{ margin: "0 0 0.75rem 0", fontSize: "1.1rem" }}>Drug Information</h3>
            <div style={{ fontSize: "1.3rem", fontWeight: "bold", marginBottom: "0.5rem", color: "var(--primary)" }}>
              {refill.drug.drug_name}
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: "0.25rem 1rem", marginBottom: "1rem" }}>
              <strong>Manufacturer:</strong>
              <span>{refill.drug.manufacturer}</span>
              <strong>Drug Class:</strong>
              <span>{refill.drug.drug_class}</span>
              <strong>Cost per unit:</strong>
              <span>${Number(refill.drug.cost).toFixed(2)}</span>
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

          {/* Right: Prescription Details */}
          <div>
            <h3 style={{ margin: "0 0 0.75rem 0", fontSize: "1.1rem" }}>Prescription</h3>
            <div style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: "0.5rem", fontSize: "0.95rem" }}>
              <strong>Quantity:</strong>
              <span>{refill.quantity}</span>

              <strong>Days Supply:</strong>
              <span>{refill.days_supply}</span>

              <strong>Total Cost:</strong>
              <span>${Number(refill.total_cost).toFixed(2)}</span>

              <strong>Priority:</strong>
              <span>{refill.priority}</span>

              <strong>Due Date:</strong>
              <span>{new Date(refill.due_date).toLocaleDateString()}</span>

              <strong>Due Time:</strong>
              <span>{new Date(refill.due_date).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>

              <strong>Source:</strong>
              <span>{refill.source}</span>

              <strong>Brand Req:</strong>
              <span>{refill.prescription.brand_required ? "Yes" : "No"}</span>
            </div>
          </div>
        </div>

        {/* Prescriber Information in the lower right */}
        {refill.prescription.prescriber && (
          <div style={{
            display: "grid",
            gridTemplateColumns: "2fr 1fr",
            gap: "2rem",
            paddingTop: "1rem",
            borderTop: "2px solid var(--bg-light)"
          }}>
            <div></div>
            <div>
              <h3 style={{ margin: "0 0 0.75rem 0", fontSize: "1.1rem" }}>Prescriber</h3>
              <div style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: "0.5rem", fontSize: "0.95rem" }}>
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
          </div>
        )}
      </div>

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
            ✓ Approve & Advance
          </button>
        )}

        {canHold && (
          <button
            className="btn btn-warning"
            onClick={handleHold}
            style={{ minWidth: "120px" }}
          >
            ⏸ Hold
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
