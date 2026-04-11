import { useEffect, useState, useContext } from "react";
import { AuthContext } from "@/context/AuthContext";
import { fetchDashboardStats } from "@/api";
import type {
  DashboardStats,
  DashboardStateSummary,
  DashboardDailyThroughput,
  DashboardTopDrug,
  DashboardPriorityBreakdown,
} from "@/types";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmt$(n: number) {
  return n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
}

function fmtN(n: number) {
  return n.toLocaleString("en-US");
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function KpiCard({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: string;
  sub?: string;
  accent?: string;
}) {
  return (
    <div
      className="card"
      style={{
        flex: 1,
        minWidth: 160,
        padding: "1.25rem 1.5rem",
        borderTop: `4px solid ${accent ?? "var(--accent)"}`,
      }}
    >
      <div style={{ fontSize: "0.75rem", color: "var(--text-light)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "0.4rem" }}>
        {label}
      </div>
      <div style={{ fontSize: "1.75rem", fontWeight: 700, color: "var(--text)", lineHeight: 1.1 }}>
        {value}
      </div>
      {sub && (
        <div style={{ fontSize: "0.8rem", color: "var(--text-light)", marginTop: "0.3rem" }}>
          {sub}
        </div>
      )}
    </div>
  );
}

// Horizontal bar chart — no library needed
function HBar({ label, value, max, color, suffix = "" }: { label: string; value: number; max: number; color: string; suffix?: string }) {
  const pct = max > 0 ? Math.round((value / max) * 100) : 0;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", minHeight: "1.6rem" }}>
      <div style={{ width: "90px", fontSize: "0.78rem", color: "var(--text-light)", textAlign: "right", flexShrink: 0 }}>
        {label}
      </div>
      <div style={{ flex: 1, background: "var(--border)", borderRadius: "4px", height: "14px", overflow: "hidden" }}>
        <div
          style={{
            width: `${pct}%`,
            height: "100%",
            background: color,
            borderRadius: "4px",
            transition: "width 0.5s ease",
          }}
        />
      </div>
      <div style={{ width: "48px", fontSize: "0.78rem", fontWeight: 600, color: "var(--text)", flexShrink: 0 }}>
        {fmtN(value)}{suffix}
      </div>
    </div>
  );
}

// Vertical bar chart for daily throughput
function ThroughputChart({ data }: { data: DashboardDailyThroughput[] }) {
  if (data.length === 0) {
    return (
      <div style={{ color: "var(--text-light)", fontSize: "0.9rem", textAlign: "center", padding: "1rem" }}>
        No fill data in the last 30 days.
      </div>
    );
  }
  const maxCount = Math.max(...data.map((d) => d.count), 1);
  return (
    <div style={{ display: "flex", alignItems: "flex-end", gap: "3px", height: "120px", overflowX: "auto" }}>
      {data.map((d) => {
        const heightPct = d.count / maxCount;
        const label = d.date.slice(5, 10); // MM-DD
        return (
          <div
            key={d.date}
            title={`${d.date.slice(0, 10)}: ${d.count} fills · ${fmt$(d.revenue)}`}
            style={{ display: "flex", flexDirection: "column", alignItems: "center", flex: "1 0 18px", minWidth: "18px", cursor: "default" }}
          >
            <div
              style={{
                width: "100%",
                background: "var(--accent)",
                borderRadius: "3px 3px 0 0",
                height: `${Math.max(Math.round(heightPct * 90), 2)}px`,
                transition: "height 0.4s ease",
              }}
            />
            <div style={{ fontSize: "0.6rem", color: "var(--text-light)", marginTop: "2px", writingMode: "vertical-rl", transform: "rotate(180deg)", height: "30px" }}>
              {label}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// State colour map
// ---------------------------------------------------------------------------

const STATE_COLORS: Record<string, string> = {
  QT:        "#00b4d8",
  QV1:       "#0096c7",
  QP:        "#0077b6",
  QV2:       "#006494",
  READY:     "#06d6a0",
  HOLD:      "#ffd166",
  SCHEDULED: "#48cae4",
  REJECTED:  "#ef476f",
  SOLD:      "#adb5bd",
  RTS:       "#dee2e6",
};

const PRIORITY_COLORS: Record<string, string> = {
  Stat:   "#ef476f",
  High:   "#ffd166",
  Normal: "#00b4d8",
  Low:    "#adb5bd",
};

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function DashboardView() {
  const { token } = useContext(AuthContext);
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    fetchDashboardStats(token)
      .then(setStats)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [token]);

  if (loading) {
    return (
      <div style={{ textAlign: "center", padding: "3rem", color: "var(--text-light)" }}>
        Loading dashboard…
      </div>
    );
  }
  if (error || !stats) {
    return (
      <div style={{ textAlign: "center", padding: "3rem", color: "var(--danger)" }}>
        {error ?? "Failed to load stats."}
      </div>
    );
  }

  const QUEUE_DISPLAY_STATES = new Set(["QT", "QV1", "QP", "QV2", "READY"]);
  const maxQueueCount = Math.max(...stats.queue_states.filter((s) => QUEUE_DISPLAY_STATES.has(s.state)).map((s) => s.count), 1);
  const maxDrugCount = Math.max(...stats.top_drugs.map((d) => d.dispense_count), 1);
  const maxPriorityCount = Math.max(...stats.priority_breakdown.map((p) => p.count), 1);

  const totalInsuranceFills = stats.insurance_split.insured + stats.insurance_split.uninsured;
  const insuredPct = totalInsuranceFills > 0
    ? Math.round((stats.insurance_split.insured / totalInsuranceFills) * 100)
    : 0;

  // State order for display — only show active pipeline states
  const STATE_ORDER = ["QT", "QV1", "QP", "QV2", "READY"];
  const sortedStates: DashboardStateSummary[] = [...stats.queue_states]
    .filter((s) => STATE_ORDER.includes(s.state))
    .sort((a, b) => STATE_ORDER.indexOf(a.state) - STATE_ORDER.indexOf(b.state));

  return (
    <div className="vstack" style={{ gap: "1.25rem" }}>

      {/* ── KPI row ── */}
      <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap" }}>
        <KpiCard label="Total Patients" value={fmtN(stats.total_patients)} accent="var(--primary)" />
        <KpiCard label="Active Prescriptions" value={fmtN(stats.total_active_prescriptions)} accent="var(--accent)" />
        <KpiCard label="In-Flight Refills" value={fmtN(stats.total_active_refills)} accent="var(--secondary)" />
        <KpiCard label="Fills Completed" value={fmtN(stats.total_fills_completed)} accent="var(--success)" />
        <KpiCard
          label="Total Revenue"
          value={fmt$(stats.total_revenue)}
          sub={`Insurance: ${fmt$(stats.total_insurance_paid)} · Copay: ${fmt$(stats.total_copay_collected)}`}
          accent="#9b59b6"
        />
        <KpiCard
          label="Rejection Rate"
          value={`${stats.rejection_rate_pct}%`}
          sub={`${fmtN(stats.total_rejected)} rejected refills`}
          accent="var(--danger)"
        />
        <KpiCard
          label="Overdue In-Queue"
          value={fmtN(stats.overdue_active_refills)}
          sub="active refills past due date"
          accent="#e63946"
        />
        <KpiCard
          label="Late Fills (30d)"
          value={fmtN(stats.late_fills_in_range)}
          sub={
            stats.fills_with_due_date_in_range > 0
              ? `${stats.late_fill_rate_pct}% of ${fmtN(stats.fills_with_due_date_in_range)} promised fills`
              : "no fills with due dates in range"
          }
          accent="#f4845f"
        />
      </div>

      {/* ── Row 2: Queue distribution + Throughput ── */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>

        {/* Queue State Distribution */}
        <div className="card" style={{ padding: "1.25rem" }}>
          <h3 style={{ margin: "0 0 1rem", fontSize: "0.9rem", color: "var(--text)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em" }}>
            Queue State Distribution
          </h3>
          <div className="vstack" style={{ gap: "0.55rem" }}>
            {sortedStates.map((s) => (
              <HBar
                key={s.state}
                label={s.state}
                value={s.count}
                max={maxQueueCount}
                color={STATE_COLORS[s.state] ?? "var(--accent)"}
              />
            ))}
            {sortedStates.length === 0 && (
              <div style={{ color: "var(--text-light)", fontSize: "0.9rem" }}>No refills yet.</div>
            )}
          </div>
          <div style={{ marginTop: "0.75rem", fontSize: "0.75rem", color: "var(--text-light)" }}>
            Pipeline stages: QT → QV1 → QP → QV2 → READY → SOLD
          </div>
        </div>

        {/* Daily Throughput */}
        <div className="card" style={{ padding: "1.25rem" }}>
          <h3 style={{ margin: "0 0 1rem", fontSize: "0.9rem", color: "var(--text)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em" }}>
            Daily Fills — Last 30 Days
          </h3>
          <ThroughputChart data={stats.daily_throughput} />
          {stats.daily_throughput.length > 0 && (
            <div style={{ marginTop: "0.6rem", fontSize: "0.75rem", color: "var(--text-light)", display: "flex", gap: "1.5rem" }}>
              <span>Avg/day: {(stats.daily_throughput.reduce((a, b) => a + b.count, 0) / stats.daily_throughput.length).toFixed(1)}</span>
              <span>Peak: {Math.max(...stats.daily_throughput.map((d) => d.count))} fills</span>
              <span>30-day rev: {fmt$(stats.daily_throughput.reduce((a, b) => a + b.revenue, 0))}</span>
            </div>
          )}
        </div>
      </div>

      {/* ── Row 3: Top Drugs + Priority + Insurance ── */}
      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr", gap: "1rem" }}>

        {/* Top Drugs */}
        <div className="card" style={{ padding: "1.25rem" }}>
          <h3 style={{ margin: "0 0 1rem", fontSize: "0.9rem", color: "var(--text)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em" }}>
            Top 10 Drugs by Dispense Volume
          </h3>
          {stats.top_drugs.length === 0 ? (
            <div style={{ color: "var(--text-light)", fontSize: "0.9rem" }}>No fill history yet.</div>
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.82rem" }}>
              <thead>
                <tr style={{ borderBottom: "2px solid var(--border)" }}>
                  <th style={{ textAlign: "left", padding: "0.3rem 0.5rem 0.5rem 0", color: "var(--text-light)", fontWeight: 600 }}>#</th>
                  <th style={{ textAlign: "left", padding: "0.3rem 0.5rem 0.5rem 0", color: "var(--text-light)", fontWeight: 600 }}>Drug</th>
                  <th style={{ textAlign: "right", padding: "0.3rem 0 0.5rem 0.5rem", color: "var(--text-light)", fontWeight: 600 }}>Fills</th>
                  <th style={{ textAlign: "right", padding: "0.3rem 0 0.5rem 0.5rem", color: "var(--text-light)", fontWeight: 600 }}>Revenue</th>
                  <th style={{ padding: "0.3rem 0 0.5rem 0.5rem", width: "80px" }}></th>
                </tr>
              </thead>
              <tbody>
                {stats.top_drugs.map((d: DashboardTopDrug, i) => (
                  <tr key={d.drug_name} style={{ borderBottom: "1px solid var(--border)" }}>
                    <td style={{ padding: "0.4rem 0.5rem 0.4rem 0", color: "var(--text-light)" }}>{i + 1}</td>
                    <td style={{ padding: "0.4rem 0.5rem", fontWeight: 500, maxWidth: "160px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {d.drug_name}
                    </td>
                    <td style={{ textAlign: "right", padding: "0.4rem 0.5rem", tabularNums: true } as React.CSSProperties}>
                      {fmtN(d.dispense_count)}
                    </td>
                    <td style={{ textAlign: "right", padding: "0.4rem 0 0.4rem 0.5rem", color: "var(--primary)" }}>
                      {fmt$(d.total_revenue)}
                    </td>
                    <td style={{ padding: "0.4rem 0 0.4rem 0.5rem" }}>
                      <div style={{ background: "var(--border)", borderRadius: "3px", height: "8px", overflow: "hidden" }}>
                        <div style={{ width: `${Math.round((d.dispense_count / maxDrugCount) * 100)}%`, height: "100%", background: "var(--accent)", borderRadius: "3px" }} />
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Priority Breakdown */}
        <div className="card" style={{ padding: "1.25rem" }}>
          <h3 style={{ margin: "0 0 1rem", fontSize: "0.9rem", color: "var(--text)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em" }}>
            Active Priority Mix
          </h3>
          <div className="vstack" style={{ gap: "0.6rem" }}>
            {["Stat", "High", "Normal", "Low"].map((p) => {
              const row: DashboardPriorityBreakdown | undefined = stats.priority_breakdown.find((r) => r.priority === p);
              return (
                <HBar
                  key={p}
                  label={p}
                  value={row?.count ?? 0}
                  max={maxPriorityCount}
                  color={PRIORITY_COLORS[p] ?? "var(--accent)"}
                />
              );
            })}
            {stats.priority_breakdown.length === 0 && (
              <div style={{ color: "var(--text-light)", fontSize: "0.9rem" }}>No active refills.</div>
            )}
          </div>
          <div style={{ marginTop: "1rem", fontSize: "0.75rem", color: "var(--text-light)" }}>
            Stat/High refills surface first in clinical queues — important for SLA modelling.
          </div>
        </div>

        {/* Insurance Split */}
        <div className="card" style={{ padding: "1.25rem" }}>
          <h3 style={{ margin: "0 0 1rem", fontSize: "0.9rem", color: "var(--text)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em" }}>
            Insurance Coverage (Fills)
          </h3>
          {totalInsuranceFills === 0 ? (
            <div style={{ color: "var(--text-light)", fontSize: "0.9rem" }}>No fill history yet.</div>
          ) : (
            <>
              {/* Donut-style split bar */}
              <div style={{ display: "flex", height: "20px", borderRadius: "10px", overflow: "hidden", marginBottom: "1rem" }}>
                <div style={{ width: `${insuredPct}%`, background: "var(--success)", transition: "width 0.5s ease" }} />
                <div style={{ flex: 1, background: "var(--border)" }} />
              </div>
              <div className="vstack" style={{ gap: "0.75rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.82rem" }}>
                  <span style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                    <span style={{ display: "inline-block", width: 10, height: 10, borderRadius: "50%", background: "var(--success)" }} />
                    Insured
                  </span>
                  <strong>{insuredPct}% ({fmtN(stats.insurance_split.insured)})</strong>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.82rem" }}>
                  <span style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                    <span style={{ display: "inline-block", width: 10, height: 10, borderRadius: "50%", background: "var(--border)" }} />
                    Self-pay
                  </span>
                  <strong>{100 - insuredPct}% ({fmtN(stats.insurance_split.uninsured)})</strong>
                </div>
                <div style={{ borderTop: "1px solid var(--border)", paddingTop: "0.5rem", fontSize: "0.78rem", color: "var(--text-light)" }}>
                  Insured revenue: {fmt$(stats.insurance_split.insured_revenue)}<br />
                  Self-pay revenue: {fmt$(stats.insurance_split.uninsured_revenue)}
                </div>
              </div>
            </>
          )}
        </div>
      </div>

      {/* ── Footer note ── */}
      <div style={{ fontSize: "0.75rem", color: "var(--text-light)", textAlign: "center", paddingBottom: "0.5rem" }}>
        All metrics computed live from the production database · Revenue figures are pre-adjudication list price · Throughput chart covers the last 30 days
      </div>
    </div>
  );
}
