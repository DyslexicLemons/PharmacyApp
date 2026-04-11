import { useContext } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchQueueSummary } from "@/api";
import type { QueuePriorityBucket } from "@/api";
import { AuthContext } from "@/context/AuthContext";

const QUEUES = ["QT", "QV1", "QP", "QV2"] as const;
type QueueKey = typeof QUEUES[number];

const QUEUE_COLORS: Record<QueueKey, { bg: string; text: string }> = {
  QT:  { bg: "#fbbf24", text: "#1a2332" },
  QV1: { bg: "#ffd166", text: "#1a2332" },
  QP:  { bg: "#00b4d8", text: "#ffffff" },
  QV2: { bg: "#a78bfa", text: "#ffffff" },
};

interface Bucket {
  key: keyof QueuePriorityBucket;
  label: string;
  color: string;
}

const BUCKETS: Bucket[] = [
  { key: "pastdue", label: "Past Due", color: "#ef476f" },
  { key: "stat",   label: "STAT",     color: "#fb923c" },
  { key: "high",   label: "High",     color: "#f5b800" },
  { key: "normal", label: "Normal",   color: "#006494" },
];

export default function QueueSidebar() {
  const { token, authUser } = useContext(AuthContext);
  const isAdmin = authUser?.isAdmin ?? false;

  const { data: summary, isLoading } = useQuery({
    queryKey: ["queue-summary", token],
    queryFn: () => fetchQueueSummary(token!),
    refetchInterval: 30_000,
    enabled: !!token,
  });

  return (
    <div
      className="card"
      style={{
        width: 220,
        flexShrink: 0,
        padding: 0,
        display: "flex",
        flexDirection: "column",
        alignSelf: "flex-start",
        overflow: "hidden",
      }}
    >
      {/* Panel header */}
      <div
        style={{
          padding: "10px 14px",
          borderBottom: "2px solid var(--border)",
          fontWeight: 700,
          fontSize: "0.72rem",
          color: "var(--primary)",
          letterSpacing: "0.08em",
          textTransform: "uppercase",
        }}
      >
        Queue Dashboard
      </div>

      {isLoading ? (
        <div style={{ padding: 14, fontSize: "0.8rem", color: "var(--text-light)" }}>
          Loading…
        </div>
      ) : (
        <div>
          {QUEUES.map((q) => {
            const { bg, text } = QUEUE_COLORS[q];
            const total = summary?.refills_by_state?.[q] ?? 0;
            const breakdown: QueuePriorityBucket = summary?.priority_breakdown?.[q] ?? { pastdue: 0, stat: 0, high: 0, normal: 0 };

            return (
              <div key={q} style={{ borderBottom: "1px solid var(--border)", padding: "8px 14px", background: `${bg}18`, borderLeft: `3px solid ${bg}` }}>
                {/* Queue name + total */}
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: total > 0 ? 6 : 0 }}>
                  <span style={{ fontWeight: 700, fontSize: "0.8rem", color: "var(--primary)" }}>
                    {q}
                  </span>
                  <span
                    style={{
                      background: bg,
                      color: text,
                      borderRadius: 999,
                      padding: "1px 8px",
                      fontSize: "0.7rem",
                      fontWeight: 700,
                    }}
                  >
                    {total}
                  </span>
                </div>

                {/* Priority breakdown rows */}
                {total === 0 ? (
                  <div style={{ fontSize: "0.72rem", color: "var(--text-light)", fontStyle: "italic" }}>
                    Empty
                  </div>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                    {BUCKETS.map(({ key, label, color }) => {
                      const count = breakdown[key];
                      if (count === 0) return null;
                      return (
                        <div
                          key={key}
                          style={{
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "space-between",
                            fontSize: "0.7rem",
                          }}
                        >
                          <span style={{ display: "flex", alignItems: "center", gap: 5, color }}>
                            <span
                              style={{
                                display: "inline-block",
                                width: 6,
                                height: 6,
                                borderRadius: "50%",
                                background: color,
                                flexShrink: 0,
                              }}
                            />
                            {label}
                          </span>
                          <span style={{ fontWeight: 700, color }}>{count}</span>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {isAdmin && summary && summary.overdue_scheduled > 0 && (
        <div style={{
          margin: "8px 10px",
          padding: "6px 10px",
          background: "#ef476f22",
          border: "1px solid #ef476f",
          borderRadius: 6,
          fontSize: "0.72rem",
          color: "#ef476f",
          fontWeight: 600,
        }}>
          ⚠ {summary.overdue_scheduled} overdue scheduled refill{summary.overdue_scheduled !== 1 ? "s" : ""} pending promotion
        </div>
      )}
    </div>
  );
}
