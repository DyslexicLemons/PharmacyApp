import { useContext } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchQueue } from "@/api";
import { AuthContext } from "@/context/AuthContext";
import type { Refill, PaginatedResponse } from "@/types";

const QUEUES = ["QT", "QV1", "QP", "QV2"] as const;
type QueueKey = typeof QUEUES[number];

const QUEUE_COLORS: Record<QueueKey, { bg: string; text: string }> = {
  QT:  { bg: "#fbbf24", text: "#1a2332" },
  QV1: { bg: "#ffd166", text: "#1a2332" },
  QP:  { bg: "#00b4d8", text: "#ffffff" },
  QV2: { bg: "#a78bfa", text: "#ffffff" },
};

interface Bucket {
  key: string;
  label: string;
  color: string;
}

const BUCKETS: Bucket[] = [
  { key: "pastdue", label: "Past Due", color: "#ef476f" },
  { key: "stat",   label: "STAT",     color: "#fb923c" },
  { key: "high",   label: "High",     color: "#f5b800" },
  { key: "normal", label: "Normal",   color: "#006494" },
];

function today(): Date {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  return d;
}

type RefillWithDue = Refill & { due_date: string; priority?: string };

function bucketKey(r: RefillWithDue): string {
  const due = new Date(r.due_date + "T00:00:00");
  if (due < today()) return "pastdue";
  const p = r.priority?.toLowerCase();
  if (p === "stat") return "stat";
  if (p === "high") return "high";
  return "normal";
}

function extractItems(result: PaginatedResponse<Refill> | Refill[]): RefillWithDue[] {
  if (Array.isArray(result)) return result as RefillWithDue[];
  return (result.items ?? []) as RefillWithDue[];
}

type QueueData = Record<QueueKey, RefillWithDue[]>;

export default function QueueSidebar() {
  const { token } = useContext(AuthContext);

  const { data, isLoading } = useQuery<QueueData>({
    queryKey: ["queue-sidebar", token],
    queryFn: () =>
      Promise.all(QUEUES.map((q) => fetchQueue(q, token!, 200, 0))).then(
        ([qt, qv1, qp, qv2]) => ({
          QT:  extractItems(qt),
          QV1: extractItems(qv1),
          QP:  extractItems(qp),
          QV2: extractItems(qv2),
        })
      ),
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
            const refills: RefillWithDue[] = data?.[q] ?? [];
            const { bg, text } = QUEUE_COLORS[q];

            const counts: Record<string, number> = Object.fromEntries(
              BUCKETS.map((b) => [b.key, 0])
            );
            refills.forEach((r) => counts[bucketKey(r)]++);

            return (
              <div key={q} style={{ borderBottom: "1px solid var(--border)", padding: "8px 14px", background: `${bg}18`, borderLeft: `3px solid ${bg}` }}>
                {/* Queue name + total */}
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: refills.length > 0 ? 6 : 0 }}>
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
                    {refills.length}
                  </span>
                </div>

                {/* Priority breakdown rows */}
                {refills.length === 0 ? (
                  <div style={{ fontSize: "0.72rem", color: "var(--text-light)", fontStyle: "italic" }}>
                    Empty
                  </div>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                    {BUCKETS.map(({ key, label, color }) => {
                      const count = counts[key];
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
    </div>
  );
}
