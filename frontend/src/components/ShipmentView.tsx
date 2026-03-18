import { useContext, useState, useEffect } from "react";
import { AuthContext } from "@/context/AuthContext";
import { DataContext } from "@/context/DataContext";
import { createShipment } from "@/api";
import { useNotification } from "@/context/NotificationContext";

export default function ShipmentView({ onBack, keyCmd, onKeyCmdHandled }) {
  const { token } = useContext(AuthContext);
  const { drugs, loadingDrugs } = useContext(DataContext);
  const { addNotification } = useNotification();

  // Items staged for the shipment
  const [items, setItems] = useState([]);

  // Add-drug form state
  const [selectedDrugId, setSelectedDrugId] = useState("");
  const [bottles, setBottles] = useState("");
  const [unitsPerBottle, setUnitsPerBottle] = useState("100");
  const [addError, setAddError] = useState("");

  // Re-auth confirm modal state
  const [showConfirm, setShowConfirm] = useState(false);
  const [confirmUsername, setConfirmUsername] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [confirmError, setConfirmError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  // "finished" command from command bar
  useEffect(() => {
    if (keyCmd === "finish") {
      if (items.length === 0) {
        addNotification("Add at least one drug before finishing the shipment.", "warning");
      } else {
        setShowConfirm(true);
      }
      onKeyCmdHandled();
    }
  }, [keyCmd]);

  function handleAddDrug() {
    setAddError("");
    if (!selectedDrugId) { setAddError("Select a drug."); return; }
    const qty = parseInt(bottles, 10);
    if (!qty || qty <= 0) { setAddError("Bottles must be a positive number."); return; }
    const units = parseInt(unitsPerBottle, 10);
    if (!units || units <= 0) { setAddError("Units per bottle must be a positive number."); return; }

    const drug = drugs.find((d) => d.id === parseInt(selectedDrugId, 10));
    if (!drug) return;

    // Prevent duplicate drug — update existing row instead
    setItems((prev) => {
      const existing = prev.find((i) => i.drug_id === drug.id);
      if (existing) {
        return prev.map((i) =>
          i.drug_id === drug.id
            ? { ...i, bottles_received: i.bottles_received + qty }
            : i
        );
      }
      return [...prev, { drug_id: drug.id, drug_name: drug.drug_name, bottles_received: qty, units_per_bottle: units }];
    });

    setSelectedDrugId("");
    setBottles("");
    setUnitsPerBottle("100");
  }

  function handleRemoveItem(drugId) {
    setItems((prev) => prev.filter((i) => i.drug_id !== drugId));
  }

  function handleFinishClick() {
    if (items.length === 0) {
      addNotification("Add at least one drug before finishing the shipment.", "warning");
      return;
    }
    setShowConfirm(true);
  }

  async function handleConfirmSubmit() {
    setConfirmError("");
    if (!confirmUsername.trim()) { setConfirmError("Username is required."); return; }
    if (!confirmPassword) { setConfirmError("Password is required."); return; }

    setSubmitting(true);
    try {
      const result = await createShipment(
        {
          items: items.map(({ drug_id, bottles_received, units_per_bottle }) => ({
            drug_id,
            bottles_received,
            units_per_bottle,
          })),
          username: confirmUsername.trim(),
          password: confirmPassword,
        },
        token
      );
      addNotification(
        `Shipment #${result.id} recorded — ${items.length} drug(s), ${items.reduce((s, i) => s + i.bottles_received, 0)} total bottles added to inventory.`,
        "success"
      );
      onBack();
    } catch (e) {
      setConfirmError(e.message);
    } finally {
      setSubmitting(false);
    }
  }

  if (loadingDrugs) return <p>Loading drugs…</p>;

  return (
    <div className="vstack">
      <h2>New Inventory Shipment</h2>
      <p style={{ color: "var(--text-light)", fontSize: "0.9rem", margin: 0 }}>
        Add each drug received in this shipment, then click <strong>Finish Shipment</strong> or type <strong>finished</strong>.
      </p>

      {/* Items staged */}
      {items.length > 0 && (
        <div className="card vstack" style={{ gap: "0.5rem" }}>
          <h3 style={{ margin: 0 }}>Staged Items</h3>
          <table className="table">
            <thead>
              <tr>
                <th>Drug</th>
                <th>Bottles</th>
                <th>Units/Bottle</th>
                <th>Total Units</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.drug_id}>
                  <td>{item.drug_name}</td>
                  <td>{item.bottles_received}</td>
                  <td>{item.units_per_bottle}</td>
                  <td>{item.bottles_received * item.units_per_bottle}</td>
                  <td>
                    <button
                      className="btn btn-secondary"
                      style={{ padding: "0.2rem 0.6rem", fontSize: "0.8rem" }}
                      onClick={() => handleRemoveItem(item.drug_id)}
                    >
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div style={{ color: "var(--text-light)", fontSize: "0.85rem" }}>
            {items.length} drug(s) &mdash; {items.reduce((s, i) => s + i.bottles_received, 0)} total bottles
          </div>
        </div>
      )}

      {/* Add drug form */}
      <div className="card vstack" style={{ gap: "1rem" }}>
        <h3 style={{ margin: 0 }}>Add Drug</h3>
        <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr", gap: "1rem" }}>
          <label>
            <strong>Drug</strong>
            <select
              value={selectedDrugId}
              onChange={(e) => setSelectedDrugId(e.target.value)}
              style={{ width: "100%", padding: "0.5rem", marginTop: "0.25rem" }}
            >
              <option value="">— Select a drug —</option>
              {drugs.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.drug_name} ({d.manufacturer})
                </option>
              ))}
            </select>
          </label>

          <label>
            <strong>Bottles Received</strong>
            <input
              type="number"
              min="1"
              value={bottles}
              onChange={(e) => setBottles(e.target.value)}
              style={{ width: "100%", padding: "0.5rem", marginTop: "0.25rem" }}
              placeholder="e.g. 5"
            />
          </label>

          <label>
            <strong>Units / Bottle</strong>
            <input
              type="number"
              min="1"
              value={unitsPerBottle}
              onChange={(e) => setUnitsPerBottle(e.target.value)}
              style={{ width: "100%", padding: "0.5rem", marginTop: "0.25rem" }}
              placeholder="e.g. 100"
            />
          </label>
        </div>

        {addError && <p style={{ color: "var(--danger)", margin: 0 }}>{addError}</p>}

        <button className="btn btn-primary" onClick={handleAddDrug} style={{ alignSelf: "flex-start" }}>
          Add Drug
        </button>
      </div>

      <div style={{ display: "flex", gap: "1rem" }}>
        <button className="btn btn-secondary" onClick={onBack}>Back</button>
        <button
          className="btn btn-success"
          onClick={handleFinishClick}
          disabled={items.length === 0}
        >
          Finish Shipment
        </button>
      </div>

      {/* Re-auth confirm modal */}
      {showConfirm && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 9000,
            backgroundColor: "rgba(0,0,0,0.65)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <div
            className="card vstack"
            style={{ width: "360px", gap: "1rem", padding: "2rem" }}
          >
            <h3 style={{ margin: 0 }}>Confirm Shipment</h3>
            <p style={{ margin: 0, color: "var(--text-light)", fontSize: "0.9rem" }}>
              Re-enter your credentials to record this shipment.
            </p>

            <label>
              <strong>Username</strong>
              <input
                type="text"
                value={confirmUsername}
                onChange={(e) => setConfirmUsername(e.target.value)}
                autoFocus
                style={{ width: "100%", padding: "0.5rem", marginTop: "0.25rem" }}
              />
            </label>

            <label>
              <strong>Password</strong>
              <input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") handleConfirmSubmit(); }}
                style={{ width: "100%", padding: "0.5rem", marginTop: "0.25rem" }}
              />
            </label>

            {confirmError && (
              <p style={{ color: "var(--danger)", margin: 0 }}>{confirmError}</p>
            )}

            <div style={{ display: "flex", gap: "1rem" }}>
              <button
                className="btn btn-secondary"
                onClick={() => { setShowConfirm(false); setConfirmError(""); setConfirmPassword(""); }}
                disabled={submitting}
              >
                Cancel
              </button>
              <button
                className="btn btn-success"
                onClick={handleConfirmSubmit}
                disabled={submitting}
              >
                {submitting ? "Submitting…" : "Confirm & Submit"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
