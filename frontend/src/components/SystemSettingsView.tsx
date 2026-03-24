import { useState, useContext, useEffect } from "react";
import { AuthContext } from "@/context/AuthContext";
import { getSystemConfig, updateSystemConfig } from "@/api";
import type { SystemConfig } from "@/types";

const BIN_MIN = 60;
const BIN_MAX = 300;
const BIN_DEFAULT = 100;

interface SystemSettingsViewProps {
  onBack?: () => void;
}

export default function SystemSettingsView({ onBack }: SystemSettingsViewProps) {
  const { token } = useContext(AuthContext);

  const [config, setConfig] = useState<SystemConfig | null>(null);
  const [binCount, setBinCount] = useState(BIN_DEFAULT);
  const [inputVal, setInputVal] = useState(String(BIN_DEFAULT));
  const [loadError, setLoadError] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [saveSuccess, setSaveSuccess] = useState("");

  useEffect(() => {
    if (!token) return;
    getSystemConfig(token)
      .then((cfg) => {
        setConfig(cfg);
        setBinCount(cfg.bin_count);
        setInputVal(String(cfg.bin_count));
      })
      .catch((err: Error) => setLoadError(err.message));
  }, [token]);

  async function handleSave(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setSaveError("");
    setSaveSuccess("");
    const val = parseInt(inputVal, 10);
    if (isNaN(val) || val < BIN_MIN || val > BIN_MAX) {
      setSaveError(`Bin count must be between ${BIN_MIN} and ${BIN_MAX}.`);
      return;
    }
    if (!token) { setSaveError("Not authenticated."); return; }
    setSaving(true);
    try {
      const merged: SystemConfig = {
        ...(config ?? { simulation_enabled: false, sim_arrival_rate: 2, sim_reject_rate: 10 }),
        bin_count: val,
      };
      const updated = await updateSystemConfig(merged, token);
      setConfig(updated);
      setBinCount(updated.bin_count);
      setInputVal(String(updated.bin_count));
      setSaveSuccess(`Bin count updated to ${updated.bin_count}.`);
    } catch (err) {
      setSaveError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="vstack" style={{ maxWidth: 520, margin: "0 auto" }}>
      <div className="hstack" style={{ justifyContent: "space-between", alignItems: "center" }}>
        <h2 style={{ margin: 0 }}>System Settings</h2>
        <button className="btn btn-secondary" onClick={onBack}>Back</button>
      </div>

      {loadError && (
        <div style={{ color: "var(--danger)", fontSize: "0.85rem" }}>{loadError}</div>
      )}

      <div className="card vstack" style={{ gap: "1rem" }}>
        <h3 style={{ margin: 0, fontSize: "1rem" }}>Ready Shelf Bins</h3>
        <p style={{ margin: 0, fontSize: "0.85rem", color: "var(--text-light)" }}>
          Number of bins available for READY prescriptions ({BIN_MIN}–{BIN_MAX}). Currently: <strong>{binCount}</strong>.
        </p>
        <form className="vstack" style={{ gap: "0.75rem" }} onSubmit={handleSave}>
          <div className="vstack" style={{ gap: "0.3rem" }}>
            <label style={{ fontSize: "0.85rem", fontWeight: 600, color: "var(--text-light)" }}>
              Bin Count
            </label>
            <input
              className="input"
              type="number"
              min={BIN_MIN}
              max={BIN_MAX}
              value={inputVal}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
                setInputVal(e.target.value);
                setSaveSuccess("");
                setSaveError("");
              }}
              style={{ maxWidth: 120 }}
            />
          </div>
          {saveError && (
            <div style={{ color: "var(--danger)", fontSize: "0.85rem" }}>{saveError}</div>
          )}
          {saveSuccess && (
            <div style={{ color: "var(--success, #06d6a0)", fontSize: "0.85rem" }}>{saveSuccess}</div>
          )}
          <button
            className="btn btn-primary"
            type="submit"
            disabled={saving}
            style={{ alignSelf: "flex-start" }}
          >
            {saving ? "Saving…" : "Save"}
          </button>
        </form>
      </div>
    </div>
  );
}
