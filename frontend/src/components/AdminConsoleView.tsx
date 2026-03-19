import { useState, useContext } from "react";
import { AuthContext } from "@/context/AuthContext";
import {
  adminGeneratePrescribers,
  adminGeneratePatients,
  adminGeneratePrescriptions,
  adminClearPrescriptions,
} from "@/api";

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

export default function AdminConsoleView({ onBack }: { onBack: () => void }) {
  const { token } = useContext(AuthContext);

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

  return (
    <div className="vstack" style={{ maxWidth: 560, margin: "0 auto" }}>
      <div className="hstack" style={{ justifyContent: "space-between", alignItems: "center" }}>
        <h2 style={{ margin: 0 }}>Admin Console</h2>
        <button className="btn btn-secondary" onClick={onBack}>Back</button>
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
