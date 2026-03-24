import { useState, useContext, useEffect } from "react";
import { AuthContext } from "@/context/AuthContext";
import {
  adminGeneratePrescribers,
  adminGeneratePatients,
  adminGeneratePrescriptions,
  adminClearPrescriptions,
  getSystemConfig,
  updateSimulationConfig,
  listSimWorkers,
  createSimWorker,
  updateSimWorker,
  deleteSimWorker,
  seedSimWorkers,
} from "@/api";
import type { SystemConfig, SimWorker } from "@/types";

const RX_STATES = ["RANDOM", "QT", "QV1", "QP", "QV2", "READY", "HOLD", "SCHEDULED", "REJECTED", "SOLD"];

interface SectionResult {
  message: string;
  isError: boolean;
}

function ResultLine({ result }: { result: SectionResult | null }) {
  if (!result) return null;
  return (
    <div style={{ fontSize: "0.85rem", color: result.isError ? "var(--danger)" : "var(--success, #06d6a0)" }}>
      {result.message}
    </div>
  );
}

function RoleBadge({ role }: { role: "technician" | "pharmacist" }) {
  const isPharm = role === "pharmacist";
  return (
    <span style={{
      fontSize: "0.7rem",
      fontWeight: 700,
      padding: "0.15rem 0.45rem",
      borderRadius: 4,
      background: isPharm ? "#6366f1" : "#0ea5e9",
      color: "#fff",
      textTransform: "uppercase",
      letterSpacing: "0.04em",
    }}>
      {isPharm ? "PharmD" : "Tech"}
    </span>
  );
}

export default function AdminConsoleView({ onBack }: { onBack: () => void }) {
  const { token } = useContext(AuthContext);

  // Simulation state
  const [simConfig, setSimConfig] = useState<SystemConfig | null>(null);
  const [simBusy, setSimBusy] = useState(false);
  const [simResult, setSimResult] = useState<SectionResult | null>(null);
  const [simArrival, setSimArrival] = useState("2");
  const [simReject, setSimReject] = useState("10");

  useEffect(() => {
    if (!token) return;
    getSystemConfig(token).then((cfg) => {
      setSimConfig(cfg);
      setSimArrival(String(cfg.sim_arrival_rate));
      setSimReject(String(cfg.sim_reject_rate));
    }).catch(() => {});
  }, [token]);

  async function handleSimToggle() {
    if (!token || !simConfig) return;
    setSimBusy(true);
    setSimResult(null);
    try {
      const updated = await updateSimulationConfig(token, {
        simulation_enabled: !simConfig.simulation_enabled,
      });
      setSimConfig(updated);
      setSimResult({
        message: updated.simulation_enabled
          ? "Simulation started. Virtual agents are now running."
          : "Simulation stopped.",
        isError: false,
      });
    } catch (err) {
      setSimResult({ message: (err as Error).message, isError: true });
    } finally {
      setSimBusy(false);
    }
  }

  async function handleSimSettings(e: React.FormEvent) {
    e.preventDefault();
    if (!token) return;
    setSimBusy(true);
    setSimResult(null);
    try {
      const updated = await updateSimulationConfig(token, {
        sim_arrival_rate: Math.max(1, Math.min(10, parseInt(simArrival, 10) || 2)),
        sim_reject_rate: Math.max(0, Math.min(50, parseInt(simReject, 10) || 10)),
      });
      setSimConfig(updated);
      setSimResult({ message: "Simulation settings saved.", isError: false });
    } catch (err) {
      setSimResult({ message: (err as Error).message, isError: true });
    } finally {
      setSimBusy(false);
    }
  }

  // ---- Workers dashboard ----
  const [workers, setWorkers] = useState<SimWorker[]>([]);
  const [workersBusy, setWorkersBusy] = useState(false);
  const [workersResult, setWorkersResult] = useState<SectionResult | null>(null);

  // New-worker form
  const [newName, setNewName] = useState("");
  const [newRole, setNewRole] = useState<"technician" | "pharmacist">("technician");
  const [newSpeed, setNewSpeed] = useState("5");

  async function loadWorkers() {
    if (!token) return;
    try {
      setWorkers(await listSimWorkers(token));
    } catch { /* silently ignore */ }
  }

  useEffect(() => { loadWorkers(); }, [token]);  // eslint-disable-line react-hooks/exhaustive-deps

  async function handleSeedWorkers() {
    if (!token) return;
    setWorkersBusy(true);
    setWorkersResult(null);
    try {
      const res = await seedSimWorkers(token);
      setWorkersResult({ message: res.message, isError: false });
      await loadWorkers();
    } catch (err) {
      setWorkersResult({ message: (err as Error).message, isError: true });
    } finally {
      setWorkersBusy(false);
    }
  }

  async function handleAddWorker(e: React.FormEvent) {
    e.preventDefault();
    if (!token || !newName.trim()) return;
    setWorkersBusy(true);
    setWorkersResult(null);
    try {
      await createSimWorker(token, {
        name: newName.trim(),
        role: newRole,
        speed: Math.max(1, Math.min(10, parseInt(newSpeed, 10) || 5)),
        is_active: true,
      });
      setNewName("");
      setNewSpeed("5");
      setWorkersResult({ message: `Added ${newRole} "${newName.trim()}".`, isError: false });
      await loadWorkers();
    } catch (err) {
      setWorkersResult({ message: (err as Error).message, isError: true });
    } finally {
      setWorkersBusy(false);
    }
  }

  async function handleToggleActive(w: SimWorker) {
    if (!token) return;
    try {
      const updated = await updateSimWorker(token, w.id, { is_active: !w.is_active });
      setWorkers((prev) => prev.map((x) => (x.id === w.id ? updated : x)));
    } catch (err) {
      setWorkersResult({ message: (err as Error).message, isError: true });
    }
  }

  async function handleSpeedChange(w: SimWorker, speed: number) {
    if (!token) return;
    try {
      const updated = await updateSimWorker(token, w.id, { speed });
      setWorkers((prev) => prev.map((x) => (x.id === w.id ? updated : x)));
    } catch (err) {
      setWorkersResult({ message: (err as Error).message, isError: true });
    }
  }

  async function handleDeleteWorker(w: SimWorker) {
    if (!token) return;
    if (!confirm(`Remove ${w.name}?`)) return;
    try {
      await deleteSimWorker(token, w.id);
      setWorkers((prev) => prev.filter((x) => x.id !== w.id));
    } catch (err) {
      setWorkersResult({ message: (err as Error).message, isError: true });
    }
  }

  // ---- Generate / Clear state ----
  const [prescriberCount, setPrescriberCount] = useState("5");
  const [prescriberResult, setPrescriberResult] = useState<SectionResult | null>(null);
  const [prescriberBusy, setPrescriberBusy] = useState(false);

  const [patientCount, setPatientCount] = useState("10");
  const [patientResult, setPatientResult] = useState<SectionResult | null>(null);
  const [patientBusy, setPatientBusy] = useState(false);

  const [rxCount, setRxCount] = useState("20");
  const [rxState, setRxState] = useState("RANDOM");
  const [rxResult, setRxResult] = useState<SectionResult | null>(null);
  const [rxBusy, setRxBusy] = useState(false);

  const [clearResult, setClearResult] = useState<SectionResult | null>(null);
  const [clearBusy, setClearBusy] = useState(false);

  async function handlePrescribers(e: React.FormEvent) {
    e.preventDefault();
    setPrescriberBusy(true);
    setPrescriberResult(null);
    try {
      const n = Math.max(1, Math.min(100, parseInt(prescriberCount, 10) || 1));
      const res = await adminGeneratePrescribers(n, token!);
      setPrescriberResult({ message: `Created ${res.prescribers_created} prescriber(s).`, isError: false });
    } catch (err) {
      setPrescriberResult({ message: (err as Error).message, isError: true });
    } finally {
      setPrescriberBusy(false);
    }
  }

  async function handlePatients(e: React.FormEvent) {
    e.preventDefault();
    setPatientBusy(true);
    setPatientResult(null);
    try {
      const n = Math.max(1, Math.min(200, parseInt(patientCount, 10) || 1));
      const res = await adminGeneratePatients(n, token!);
      setPatientResult({ message: `Created ${res.patients_created} patient(s).`, isError: false });
    } catch (err) {
      setPatientResult({ message: (err as Error).message, isError: true });
    } finally {
      setPatientBusy(false);
    }
  }

  async function handlePrescriptions(e: React.FormEvent) {
    e.preventDefault();
    setRxBusy(true);
    setRxResult(null);
    try {
      const n = Math.max(1, Math.min(500, parseInt(rxCount, 10) || 1));
      const res = await adminGeneratePrescriptions(n, rxState, token!);
      const stateLabel = res.state === "RANDOM" ? "mixed states" : res.state;
      setRxResult({
        message: `Created ${res.prescriptions_created} prescription(s) — ${res.refills_created} active refills, ${res.refill_history_created} sold (${stateLabel}).`,
        isError: false,
      });
    } catch (err) {
      setRxResult({ message: (err as Error).message, isError: true });
    } finally {
      setRxBusy(false);
    }
  }

  async function handleClear() {
    if (!confirm("This will permanently delete ALL prescriptions, refills, and refill history. Continue?")) return;
    setClearBusy(true);
    setClearResult(null);
    try {
      const res = await adminClearPrescriptions(token!);
      setClearResult({
        message: `Deleted: ${res.prescriptions_deleted} prescription(s), ${res.refills_deleted} refill(s), ${res.refill_history_deleted} history record(s).`,
        isError: false,
      });
    } catch (err) {
      setClearResult({ message: (err as Error).message, isError: true });
    } finally {
      setClearBusy(false);
    }
  }

  const techs = workers.filter((w) => w.role === "technician");
  const pharmacists = workers.filter((w) => w.role === "pharmacist");

  return (
    <div className="vstack" style={{ maxWidth: 640, margin: "0 auto" }}>
      <div className="hstack" style={{ justifyContent: "space-between", alignItems: "center" }}>
        <h2 style={{ margin: 0 }}>Admin Console</h2>
        <button className="btn btn-secondary" onClick={onBack}>Back</button>
      </div>

      {/* Simulation Control */}
      <div className="card vstack" style={{ gap: "0.75rem", border: simConfig?.simulation_enabled ? "2px solid var(--success, #06d6a0)" : undefined }}>
        <div className="hstack" style={{ justifyContent: "space-between", alignItems: "center" }}>
          <h3 style={{ margin: 0, fontSize: "1rem" }}>Virtual Pharmacy Simulation</h3>
          <span style={{
            fontSize: "0.75rem",
            fontWeight: 700,
            padding: "0.2rem 0.6rem",
            borderRadius: 4,
            background: simConfig?.simulation_enabled ? "var(--success, #06d6a0)" : "var(--text-light)",
            color: simConfig?.simulation_enabled ? "#000" : "#fff",
          }}>
            {simConfig === null ? "…" : simConfig.simulation_enabled ? "RUNNING" : "STOPPED"}
          </span>
        </div>
        <p style={{ margin: 0, fontSize: "0.85rem", color: "var(--text-light)" }}>
          Virtual patients, technicians, and pharmacists work the queue automatically.
          Patients arrive every 2 min; technicians and pharmacists act every minute.
        </p>

        <div className="hstack" style={{ gap: "0.5rem", flexWrap: "wrap" }}>
          <button
            className="btn btn-primary"
            onClick={handleSimToggle}
            disabled={simBusy || simConfig === null}
            style={simConfig?.simulation_enabled ? { background: "var(--danger)", border: "none" } : {}}
          >
            {simBusy ? "…" : simConfig?.simulation_enabled ? "Stop Simulation" : "Start Simulation"}
          </button>
        </div>

        <form className="hstack" style={{ gap: "1rem", flexWrap: "wrap", alignItems: "flex-end" }} onSubmit={handleSimSettings}>
          <div className="vstack" style={{ gap: "0.25rem" }}>
            <label style={{ fontSize: "0.8rem", fontWeight: 600, color: "var(--text-light)" }}>
              Arrival rate (max Rxs / 2 min)
            </label>
            <input
              className="input"
              type="number"
              min={1}
              max={10}
              value={simArrival}
              onChange={(e) => setSimArrival(e.target.value)}
              style={{ maxWidth: 80 }}
            />
          </div>
          <div className="vstack" style={{ gap: "0.25rem" }}>
            <label style={{ fontSize: "0.8rem", fontWeight: 600, color: "var(--text-light)" }}>
              Reject rate % (pharmacist QV1)
            </label>
            <input
              className="input"
              type="number"
              min={0}
              max={50}
              value={simReject}
              onChange={(e) => setSimReject(e.target.value)}
              style={{ maxWidth: 80 }}
            />
          </div>
          <button className="btn btn-secondary" type="submit" disabled={simBusy}>
            Save Settings
          </button>
        </form>

        <ResultLine result={simResult} />
      </div>

      {/* Virtual Workers Dashboard */}
      <div className="card vstack" style={{ gap: "0.75rem" }}>
        <div className="hstack" style={{ justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "0.5rem" }}>
          <h3 style={{ margin: 0, fontSize: "1rem" }}>Virtual Workers</h3>
          <div className="hstack" style={{ gap: "0.5rem" }}>
            <span style={{ fontSize: "0.8rem", color: "var(--text-light)" }}>
              {techs.filter((w) => w.is_active).length}/{techs.length} techs active
              &nbsp;·&nbsp;
              {pharmacists.filter((w) => w.is_active).length}/{pharmacists.length} pharmacists active
            </span>
            <button
              className="btn btn-secondary"
              style={{ fontSize: "0.8rem", padding: "0.25rem 0.6rem" }}
              onClick={handleSeedWorkers}
              disabled={workersBusy}
            >
              Seed Defaults
            </button>
          </div>
        </div>
        <p style={{ margin: 0, fontSize: "0.85rem", color: "var(--text-light)" }}>
          Each worker processes <strong>speed</strong> refills per queue per minute.
          Inactive workers are benched but not deleted.
        </p>

        {workers.length === 0 ? (
          <div style={{ fontSize: "0.85rem", color: "var(--text-light)" }}>
            No workers yet — click <strong>Seed Defaults</strong> to add 2 techs and 1 pharmacist.
          </div>
        ) : (
          <div className="vstack" style={{ gap: "0.35rem" }}>
            {/* Technicians */}
            {techs.length > 0 && (
              <div style={{ fontSize: "0.75rem", fontWeight: 700, color: "var(--text-light)", textTransform: "uppercase", letterSpacing: "0.06em", marginTop: "0.25rem" }}>
                Technicians
              </div>
            )}
            {techs.map((w) => (
              <WorkerRow key={w.id} worker={w} onToggle={handleToggleActive} onSpeed={handleSpeedChange} onDelete={handleDeleteWorker} />
            ))}

            {/* Pharmacists */}
            {pharmacists.length > 0 && (
              <div style={{ fontSize: "0.75rem", fontWeight: 700, color: "var(--text-light)", textTransform: "uppercase", letterSpacing: "0.06em", marginTop: "0.5rem" }}>
                Pharmacists
              </div>
            )}
            {pharmacists.map((w) => (
              <WorkerRow key={w.id} worker={w} onToggle={handleToggleActive} onSpeed={handleSpeedChange} onDelete={handleDeleteWorker} />
            ))}
          </div>
        )}

        {/* Add new worker form */}
        <form className="hstack" style={{ gap: "0.5rem", flexWrap: "wrap", alignItems: "flex-end", borderTop: "1px solid var(--border)", paddingTop: "0.75rem" }} onSubmit={handleAddWorker}>
          <div className="vstack" style={{ gap: "0.25rem" }}>
            <label style={{ fontSize: "0.8rem", fontWeight: 600, color: "var(--text-light)" }}>Name</label>
            <input
              className="input"
              type="text"
              placeholder="e.g. Dr. Kim"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              style={{ minWidth: 130 }}
              required
            />
          </div>
          <div className="vstack" style={{ gap: "0.25rem" }}>
            <label style={{ fontSize: "0.8rem", fontWeight: 600, color: "var(--text-light)" }}>Role</label>
            <select
              className="input"
              value={newRole}
              onChange={(e) => setNewRole(e.target.value as "technician" | "pharmacist")}
            >
              <option value="technician">Technician</option>
              <option value="pharmacist">Pharmacist</option>
            </select>
          </div>
          <div className="vstack" style={{ gap: "0.25rem" }}>
            <label style={{ fontSize: "0.8rem", fontWeight: 600, color: "var(--text-light)" }}>Speed (1–10)</label>
            <input
              className="input"
              type="number"
              min={1}
              max={10}
              value={newSpeed}
              onChange={(e) => setNewSpeed(e.target.value)}
              style={{ maxWidth: 70 }}
            />
          </div>
          <button className="btn btn-primary" type="submit" disabled={workersBusy || !newName.trim()}>
            Add Worker
          </button>
        </form>

        <ResultLine result={workersResult} />
      </div>

      {/* Generate Prescribers */}
      <div className="card vstack" style={{ gap: "0.75rem" }}>
        <h3 style={{ margin: 0, fontSize: "1rem" }}>Generate Prescribers</h3>
        <p style={{ margin: 0, fontSize: "0.85rem", color: "var(--text-light)" }}>
          Add random prescribers to the database (max 100).
        </p>
        <form className="hstack" style={{ gap: "0.5rem", alignItems: "flex-end" }} onSubmit={handlePrescribers}>
          <div className="vstack" style={{ gap: "0.25rem" }}>
            <label style={{ fontSize: "0.8rem", fontWeight: 600, color: "var(--text-light)" }}>Count</label>
            <input
              className="input"
              type="number"
              min={1}
              max={100}
              value={prescriberCount}
              onChange={(e) => { setPrescriberCount(e.target.value); setPrescriberResult(null); }}
              style={{ maxWidth: 80 }}
            />
          </div>
          <button className="btn btn-primary" type="submit" disabled={prescriberBusy}>
            {prescriberBusy ? "Generating…" : "Generate"}
          </button>
        </form>
        <ResultLine result={prescriberResult} />
      </div>

      {/* Generate Patients */}
      <div className="card vstack" style={{ gap: "0.75rem" }}>
        <h3 style={{ margin: 0, fontSize: "1rem" }}>Generate Patients</h3>
        <p style={{ margin: 0, fontSize: "0.85rem", color: "var(--text-light)" }}>
          Add random patients to the database (max 200).
        </p>
        <form className="hstack" style={{ gap: "0.5rem", alignItems: "flex-end" }} onSubmit={handlePatients}>
          <div className="vstack" style={{ gap: "0.25rem" }}>
            <label style={{ fontSize: "0.8rem", fontWeight: 600, color: "var(--text-light)" }}>Count</label>
            <input
              className="input"
              type="number"
              min={1}
              max={200}
              value={patientCount}
              onChange={(e) => { setPatientCount(e.target.value); setPatientResult(null); }}
              style={{ maxWidth: 80 }}
            />
          </div>
          <button className="btn btn-primary" type="submit" disabled={patientBusy}>
            {patientBusy ? "Generating…" : "Generate"}
          </button>
        </form>
        <ResultLine result={patientResult} />
      </div>

      {/* Generate Prescriptions */}
      <div className="card vstack" style={{ gap: "0.75rem" }}>
        <h3 style={{ margin: 0, fontSize: "1rem" }}>Generate Prescriptions</h3>
        <p style={{ margin: 0, fontSize: "0.85rem", color: "var(--text-light)" }}>
          Add prescriptions with refills in the selected queue state (max 500). Requires patients, prescribers, and drugs to exist.
        </p>
        <form className="hstack" style={{ gap: "0.5rem", alignItems: "flex-end" }} onSubmit={handlePrescriptions}>
          <div className="vstack" style={{ gap: "0.25rem" }}>
            <label style={{ fontSize: "0.8rem", fontWeight: 600, color: "var(--text-light)" }}>Count</label>
            <input
              className="input"
              type="number"
              min={1}
              max={500}
              value={rxCount}
              onChange={(e) => { setRxCount(e.target.value); setRxResult(null); }}
              style={{ maxWidth: 80 }}
            />
          </div>
          <div className="vstack" style={{ gap: "0.25rem" }}>
            <label style={{ fontSize: "0.8rem", fontWeight: 600, color: "var(--text-light)" }}>State</label>
            <select
              className="input"
              value={rxState}
              onChange={(e) => { setRxState(e.target.value); setRxResult(null); }}
              style={{ minWidth: 120 }}
            >
              {RX_STATES.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>
          <button className="btn btn-primary" type="submit" disabled={rxBusy}>
            {rxBusy ? "Generating…" : "Generate"}
          </button>
        </form>
        <ResultLine result={rxResult} />
      </div>

      {/* Clear All Prescriptions */}
      <div className="card vstack" style={{ gap: "0.75rem" }}>
        <h3 style={{ margin: 0, fontSize: "1rem" }}>Clear All Prescriptions</h3>
        <p style={{ margin: 0, fontSize: "0.85rem", color: "var(--text-light)" }}>
          Permanently deletes all refills, refill history, and prescriptions. Does not affect patients, prescribers, or drugs.
        </p>
        <div>
          <button
            className="btn"
            style={{ background: "var(--danger)", color: "#fff", border: "none" }}
            onClick={handleClear}
            disabled={clearBusy}
          >
            {clearBusy ? "Clearing…" : "Clear All Prescriptions"}
          </button>
        </div>
        <ResultLine result={clearResult} />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// WorkerRow sub-component
// ---------------------------------------------------------------------------

function WorkerRow({
  worker,
  onToggle,
  onSpeed,
  onDelete,
}: {
  worker: SimWorker;
  onToggle: (w: SimWorker) => void;
  onSpeed: (w: SimWorker, speed: number) => void;
  onDelete: (w: SimWorker) => void;
}) {
  return (
    <div
      className="hstack"
      style={{
        gap: "0.75rem",
        alignItems: "center",
        padding: "0.4rem 0.5rem",
        borderRadius: 6,
        background: worker.is_active ? "var(--bg-card, #1e1e2e)" : "var(--bg, #13131f)",
        opacity: worker.is_active ? 1 : 0.5,
        flexWrap: "wrap",
      }}
    >
      <RoleBadge role={worker.role} />
      <span style={{ flex: 1, fontWeight: 500, fontSize: "0.9rem", minWidth: 100, color: "#e2e8f0" }}>
        {worker.name}
      </span>

      {/* Speed slider */}
      <div className="hstack" style={{ gap: "0.4rem", alignItems: "center" }}>
        <label style={{ fontSize: "0.75rem", color: "#e2e8f0", whiteSpace: "nowrap" }}>
          Speed {worker.speed}
        </label>
        <input
          type="range"
          min={1}
          max={10}
          value={worker.speed}
          onChange={(e) => onSpeed(worker, parseInt(e.target.value, 10))}
          style={{ width: 80, accentColor: worker.role === "pharmacist" ? "#6366f1" : "#0ea5e9" }}
        />
      </div>

      {/* Active toggle */}
      <button
        className="btn btn-secondary"
        style={{ fontSize: "0.75rem", padding: "0.2rem 0.5rem" }}
        onClick={() => onToggle(worker)}
      >
        {worker.is_active ? "Bench" : "Activate"}
      </button>

      {/* Delete */}
      <button
        className="btn"
        style={{ fontSize: "0.75rem", padding: "0.2rem 0.5rem", background: "transparent", color: "var(--danger)", border: "1px solid var(--danger)" }}
        onClick={() => onDelete(worker)}
      >
        Remove
      </button>
    </div>
  );
}
