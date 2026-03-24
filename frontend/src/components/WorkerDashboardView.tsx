import { useContext, useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AuthContext } from "@/context/AuthContext";
import { listSimWorkers, fetchQueueSummary } from "@/api";
import type { SimWorker } from "@/types";

interface Props {
  onBack: () => void;
}

type StationKey = "triage" | "fill" | "verify_1" | "verify_2" | "window";

const STATION_LABELS: Record<StationKey, string> = {
  triage:   "Triage (QT)",
  fill:     "Fill (QP)",
  verify_1: "Verify 1 (QV1)",
  verify_2: "Verify 2 (QV2)",
  window:   "Window (READY)",
};

const STATION_QUEUE_KEY: Record<StationKey, string> = {
  triage:   "QT",
  fill:     "QP",
  verify_1: "QV1",
  verify_2: "QV2",
  window:   "READY",
};

const STATION_COLOR: Record<StationKey, string> = {
  triage:   "#fbbf24",
  fill:     "#00b4d8",
  verify_1: "#ffd166",
  verify_2: "#a78bfa",
  window:   "#06d6a0",
};

function stationColor(station: string | null): string {
  if (!station) return "#94a3b8";
  return STATION_COLOR[station as StationKey] ?? "#94a3b8";
}

function stationLabel(station: string | null): string {
  if (!station) return "—";
  return STATION_LABELS[station as StationKey] ?? station;
}

// Returns seconds remaining, counting down from a server-provided baseline.
// secsBase: secs_remaining as of fetchedAt; counts down using client wall clock since then.
function localSecsRemaining(secsBase: number, fetchedAt: number): number {
  return Math.max(0, secsBase - (Date.now() - fetchedAt) / 1000);
}

// Returns progress 0–100, extrapolated from server-provided baseline.
function localProgress(pctBase: number, secsBase: number, fetchedAt: number): number {
  if (secsBase <= 0) return 100;
  const elapsed = (Date.now() - fetchedAt) / 1000;
  // Rate of progress per second at the time of the snapshot
  const rate = (100 - pctBase) / secsBase;
  return Math.min(100, pctBase + rate * elapsed);
}

function formatCountdown(secs: number): string {
  if (secs <= 0) return "";
  if (secs >= 60) {
    return `${Math.floor(secs / 60)}m ${secs % 60}s`;
  }
  return `${secs}s`;
}

function TravelProgressBar({ pct }: { pct: number }) {
  return (
    <div style={{
      height: 4,
      borderRadius: 2,
      background: "rgba(255,255,255,0.1)",
      overflow: "hidden",
      marginTop: 4,
    }}>
      <div style={{
        height: "100%",
        width: `${pct}%`,
        background: "#fb923c",
        borderRadius: 2,
        transition: "width 0.2s linear",
      }} />
    </div>
  );
}

function WorkerStatusBadge({ worker }: { worker: SimWorker }) {
  // fetchedAt tracks when we received the server snapshot so we can extrapolate locally.
  const fetchedAt = useState(() => Date.now())[0];
  const fetchedAtRef = { current: fetchedAt };

  const secsBase = worker.secs_remaining ?? 0;
  const pctBase = worker.progress_pct ?? 0;

  const [secsLeft, setSecsLeft] = useState(() =>
    secsBase > 0 ? localSecsRemaining(secsBase, fetchedAtRef.current) : 0
  );
  const [pct, setPct] = useState(() =>
    secsBase > 0 ? localProgress(pctBase, secsBase, fetchedAtRef.current) : null
  );

  useEffect(() => {
    const now = Date.now();
    if (secsBase <= 0) {
      setSecsLeft(0);
      setPct(null);
      return;
    }
    setSecsLeft(localSecsRemaining(secsBase, now));
    setPct(localProgress(pctBase, secsBase, now));
    const id = setInterval(() => {
      const s = localSecsRemaining(secsBase, now);
      setSecsLeft(s);
      setPct(localProgress(pctBase, secsBase, now));
      if (s <= 0) clearInterval(id);
    }, 200);
    return () => clearInterval(id);
  }, [secsBase, pctBase]);

  if (!worker.is_active) {
    return (
      <span style={{ color: "#94a3b8", fontSize: "0.8rem", fontStyle: "italic" }}>
        Benched
      </span>
    );
  }

  if (secsLeft > 0 && worker.current_refill) {
    return (
      <div style={{ flex: 1 }}>
        <span style={{ color: "#06d6a0", fontSize: "0.8rem" }}>
          Working — {formatCountdown(Math.round(secsLeft))} left
        </span>
        {pct !== null && (
          <div style={{
            height: 4,
            borderRadius: 2,
            background: "rgba(255,255,255,0.1)",
            overflow: "hidden",
            marginTop: 4,
          }}>
            <div style={{
              height: "100%",
              width: `${pct}%`,
              background: "#06d6a0",
              borderRadius: 2,
              transition: "width 0.2s linear",
            }} />
          </div>
        )}
      </div>
    );
  }

  if (secsLeft > 0) {
    return (
      <div style={{ flex: 1 }}>
        <span style={{ color: "#fb923c", fontSize: "0.8rem" }}>
          Traveling — {formatCountdown(Math.round(secsLeft))} left
        </span>
        {pct !== null && <TravelProgressBar pct={pct} />}
      </div>
    );
  }

  // Timer expired but Celery hasn't cleared current_refill yet — show 100% bar
  if (worker.current_refill && worker.busy_until) {
    return (
      <div style={{ flex: 1 }}>
        <span style={{ color: "#06d6a0", fontSize: "0.8rem" }}>Finishing…</span>
        <div style={{
          height: 4,
          borderRadius: 2,
          background: "rgba(255,255,255,0.1)",
          overflow: "hidden",
          marginTop: 4,
        }}>
          <div style={{
            height: "100%",
            width: "100%",
            background: "#06d6a0",
            borderRadius: 2,
          }} />
        </div>
      </div>
    );
  }

  if (worker.current_station && worker.current_refill) {
    return (
      <span style={{ color: "#06d6a0", fontSize: "0.8rem" }}>
        Working
      </span>
    );
  }

  if (worker.current_station) {
    return (
      <span style={{ color: "#94a3b8", fontSize: "0.8rem" }}>
        Idle at station
      </span>
    );
  }

  return (
    <span style={{ color: "#94a3b8", fontSize: "0.8rem" }}>
      Idle
    </span>
  );
}

function WorkerCard({ worker, queueCounts }: { worker: SimWorker; queueCounts: Record<string, number> }) {
  const queueKey = worker.current_station
    ? STATION_QUEUE_KEY[worker.current_station as StationKey]
    : null;
  const queueCount = queueKey ? (queueCounts[queueKey] ?? 0) : null;
  const color = stationColor(worker.current_station);

  return (
    <div
      style={{
        background: "var(--bg-card, #1e2d3d)",
        border: `1px solid ${worker.is_active ? color : "var(--border-color, #2a3f55)"}`,
        borderRadius: 8,
        padding: "14px 18px",
        opacity: worker.is_active ? 1 : 0.55,
        display: "flex",
        flexDirection: "column",
        gap: 8,
      }}
    >
      {/* Header row */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
        <span style={{ fontWeight: 700, fontSize: "1rem", color: "#e2e8f0" }}>{worker.name}</span>
        <span
          style={{
            fontSize: "0.72rem",
            fontWeight: 600,
            padding: "2px 8px",
            borderRadius: 20,
            background: worker.role === "pharmacist" ? "rgba(167,139,250,0.15)" : "rgba(0,180,216,0.15)",
            color: worker.role === "pharmacist" ? "#a78bfa" : "#00b4d8",
            textTransform: "uppercase",
            letterSpacing: "0.06em",
          }}
        >
          {worker.role}
        </span>
      </div>

      {/* Station row */}
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span
          style={{
            width: 10,
            height: 10,
            borderRadius: "50%",
            background: worker.is_active ? color : "var(--text-light)",
            flexShrink: 0,
          }}
        />
        <span style={{ fontSize: "0.88rem", color: worker.is_active ? color : "var(--text-light)" }}>
          {worker.current_station ? stationLabel(worker.current_station) : "No station"}
        </span>
        {queueCount !== null && worker.is_active && (
          <span style={{ fontSize: "0.75rem", color: "#94a3b8", marginLeft: "auto" }}>
            {queueCount} in queue
          </span>
        )}
      </div>

      {/* Current refill row */}
      {worker.is_active && worker.current_refill && (
        <div style={{
          fontSize: "0.75rem",
          color: "#cbd5e1",
          background: "rgba(255,255,255,0.05)",
          borderRadius: 4,
          padding: "4px 8px",
          lineHeight: 1.4,
        }}>
          <span style={{ color: "#94a3b8" }}>Working: </span>
          <span style={{ fontWeight: 600 }}>Rx #{worker.current_refill.prescription_id}</span>
          <span style={{ color: "#94a3b8" }}> · </span>
          {worker.current_refill.drug_name}
          <span style={{ color: "#94a3b8" }}> / </span>
          {worker.current_refill.patient_name}
        </div>
      )}

      {/* Status row */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <WorkerStatusBadge worker={worker} />
        <span style={{ fontSize: "0.75rem", color: "#94a3b8" }}>
          Speed {worker.speed}/10
        </span>
      </div>
    </div>
  );
}

function StationSummary({ queueCounts }: { queueCounts: Record<string, number> }) {
  const stations: { station: StationKey; label: string; state: string }[] = [
    { station: "triage",   label: "Triage",   state: "QT" },
    { station: "verify_1", label: "Verify 1", state: "QV1" },
    { station: "fill",     label: "Fill",     state: "QP" },
    { station: "verify_2", label: "Verify 2", state: "QV2" },
    { station: "window",   label: "Window",   state: "READY" },
  ];

  return (
    <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 24 }}>
      {stations.map(({ station, label, state }) => {
        const count = queueCounts[state] ?? 0;
        const color = STATION_COLOR[station];
        return (
          <div
            key={station}
            style={{
              flex: "1 1 80px",
              minWidth: 80,
              background: "var(--bg-card, #1e2d3d)",
              border: `1px solid ${color}40`,
              borderRadius: 8,
              padding: "10px 14px",
              textAlign: "center",
            }}
          >
            <div style={{ fontSize: "1.5rem", fontWeight: 800, color }}>{count}</div>
            <div style={{ fontSize: "0.75rem", color: "#94a3b8", marginTop: 2 }}>{label}</div>
          </div>
        );
      })}
    </div>
  );
}

export default function WorkerDashboardView({ onBack }: Props) {
  const { token } = useContext(AuthContext);

  const { data: workers = [], isLoading: loadingWorkers } = useQuery<SimWorker[]>({
    queryKey: ["worker-dashboard-workers"],
    queryFn: () => listSimWorkers(token!),
    refetchInterval: 1000,
    enabled: !!token,
  });

  const { data: summary } = useQuery({
    queryKey: ["worker-dashboard-summary"],
    queryFn: () => fetchQueueSummary(token!),
    refetchInterval: 2000,
    enabled: !!token,
  });

  const queueCounts: Record<string, number> = summary?.refills_by_state ?? {};

  const technicians = workers.filter((w) => w.role === "technician");
  const pharmacists = workers.filter((w) => w.role === "pharmacist");

  const activeCount = workers.filter((w) => w.is_active).length;

  return (
    <div className="vstack" style={{ gap: 0 }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 20 }}>
        <button className="btn btn-secondary" onClick={onBack} style={{ padding: "4px 12px", fontSize: "0.85rem" }}>
          ← Back
        </button>
        <h2 style={{ margin: 0, fontSize: "1.2rem" }}>Worker Dashboard</h2>
        <span style={{ marginLeft: "auto", fontSize: "0.8rem", color: "#94a3b8" }}>
          {activeCount}/{workers.length} active · live
        </span>
      </div>

      {/* Queue counts */}
      <StationSummary queueCounts={queueCounts} />

      {loadingWorkers && (
        <div style={{ color: "var(--text-light)", textAlign: "center", padding: "2rem" }}>Loading…</div>
      )}

      {!loadingWorkers && workers.length === 0 && (
        <div style={{ color: "var(--text-light)", textAlign: "center", padding: "2rem" }}>
          No workers found. Use <strong>admin</strong> to add workers.
        </div>
      )}

      {/* Technicians */}
      {technicians.length > 0 && (
        <div style={{ marginBottom: 24 }}>
          <div style={{ fontSize: "0.75rem", fontWeight: 700, color: "#00b4d8", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 10 }}>
            Technicians ({technicians.filter((w) => w.is_active).length}/{technicians.length} active)
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 10 }}>
            {technicians.map((w) => (
              <WorkerCard key={w.id} worker={w} queueCounts={queueCounts} />
            ))}
          </div>
        </div>
      )}

      {/* Pharmacists */}
      {pharmacists.length > 0 && (
        <div>
          <div style={{ fontSize: "0.75rem", fontWeight: 700, color: "#a78bfa", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 10 }}>
            Pharmacists ({pharmacists.filter((w) => w.is_active).length}/{pharmacists.length} active)
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 10 }}>
            {pharmacists.map((w) => (
              <WorkerCard key={w.id} worker={w} queueCounts={queueCounts} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
