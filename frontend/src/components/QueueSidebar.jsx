import { useContext } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchQueue } from "@/api";
import { AuthContext } from "@/context/AuthContext";

const QUEUES = ["QT", "QV1", "QP", "QV2"];

const QUEUE_COLORS = {
  QT:  { bg: "#fbbf24", text: "#1a2332" },
  QV1: { bg: "#ffd166", text: "#1a2332" },
  QP:  { bg: "#00b4d8", text: "#ffffff" },
  QV2: { bg: "#a78bfa", text: "#ffffff" },
};

// Each item falls into exactly one bucket (past due takes precedence over priority).
const BUCKETS = [
  { key: "pastdue", label: "Past Due", short: "PD",  color: "#ef476f" },
  { key: "stat",   label: "< 15 min", short: "<15",  color: "#fb923c" },
  { key: "high",   label: "< 30 min", short: "<30",  color: "#f5b800" },
  { key: "normal", label: "< 60 min", short: "<60",  color: "#006494" },
];

function today() {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  return d;
}

function bucketKey(r) {
  const due = new Date(r.due_date + "T00:00:00");
  if (due < today()) return "pastdue";
  const p = r.priority?.toLowerCase();
  if (p === "stat")   return "stat";
  if (p === "high")   return "high";
  return "normal"; // "normal", "low", or anything else
}

function formatDue(dueDateStr) {
  const t = today();
  const due = new Date(dueDateStr + "T00:00:00");
  const diff = Math.round((due - t) / 86_400_000);
  if (diff < 0)   return { label: `${Math.abs(diff)}d overdue`, overdue: true };
  if (diff === 0) return { label: "Today",    overdue: false };
  if (diff === 1) return { label: "Tomorrow", overdue: false };
  return { label: `${diff}d`, overdue: false };
}

export default function QueueSidebar() {
  const { token } = useContext(AuthContext);

  const { data, isLoading } = useQuery({
    queryKey: ["queue-sidebar", token],
    queryFn: () =>
      Promise.all(QUEUES.map((q) => fetchQueue(q, token, 200, 0))).then(
        ([qt, qv1, qp, qv2]) => ({
          QT:  qt.items  ?? qt,
          QV1: qv1.items ?? qv1,
          QP:  qp.items  ?? qp,
          QV2: qv2.items ?? qv2,
        })
      ),
    refetchInterval: 30_000,
    enabled: !!token,
  });

  return (
    <div
      className="card"
      style={{
        width: 252,
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
            const refills = data?.[q] ?? [];
            const { bg, text } = QUEUE_COLORS[q];

            // Group items into buckets
            const grouped = Object.fromEntries(BUCKETS.map((b) => [b.key, []]));
            refills.forEach((r) => grouped[bucketKey(r)].push(r));

            return (
              <div key={q} style={{ borderBottom: "1px solid var(--border)" }}>
                {/* Queue header row */}
                <div
                  style={{
                    padding: "7px 14px",
                    background: `${bg}22`,
                    borderLeft: `3px solid ${bg}`,
                  }}
                >
                  {/* Queue name + total */}
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      marginBottom: refills.length > 0 ? 5 : 0,
                    }}
                  >
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

                  {/* Bucket count breakdown */}
                  {refills.length > 0 && (
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                      {BUCKETS.map(({ key, short, color }) => {
                        const count = grouped[key].length;
                        if (count === 0) return null;
                        return (
                          <span
                            key={key}
                            style={{
                              fontSize: "0.62rem",
                              fontWeight: 700,
                              color,
                              background: `${color}18`,
                              border: `1px solid ${color}55`,
                              borderRadius: 4,
                              padding: "1px 5px",
                              whiteSpace: "nowrap",
                            }}
                          >
                            {short}: {count}
                          </span>
                        );
                      })}
                    </div>
                  )}
                </div>

                {/* Item listings per bucket */}
                {refills.length === 0 ? (
                  <div
                    style={{
                      padding: "5px 14px 7px",
                      fontSize: "0.72rem",
                      color: "var(--text-light)",
                      fontStyle: "italic",
                    }}
                  >
                    Empty
                  </div>
                ) : (
                  BUCKETS.map(({ key, label, color }) => {
                    const items = grouped[key];
                    if (items.length === 0) return null;
                    return (
                      <div key={key} style={{ padding: "5px 14px" }}>
                        {/* Bucket label */}
                        <div
                          style={{
                            fontSize: "0.65rem",
                            fontWeight: 700,
                            color,
                            textTransform: "uppercase",
                            letterSpacing: "0.06em",
                            marginBottom: 3,
                            display: "flex",
                            alignItems: "center",
                            gap: 5,
                          }}
                        >
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
                          <span style={{ marginLeft: "auto", color: "var(--text-light)", fontWeight: 400 }}>
                            {items.length}
                          </span>
                        </div>

                        {/* Item rows */}
                        {items.map((r) => {
                          const due = formatDue(r.due_date);
                          return (
                            <div
                              key={r.id}
                              style={{
                                fontSize: "0.7rem",
                                padding: "2px 0 2px 11px",
                                borderLeft: "2px solid var(--border)",
                                marginBottom: 2,
                                display: "flex",
                                justifyContent: "space-between",
                                alignItems: "center",
                                gap: 4,
                              }}
                            >
                              <div style={{ minWidth: 0, flex: 1 }}>
                                <div
                                  style={{
                                    fontWeight: 600,
                                    overflow: "hidden",
                                    textOverflow: "ellipsis",
                                    whiteSpace: "nowrap",
                                  }}
                                >
                                  {r.patient.last_name}, {r.patient.first_name[0]}.
                                </div>
                                <div
                                  style={{
                                    color: "var(--text-light)",
                                    overflow: "hidden",
                                    textOverflow: "ellipsis",
                                    whiteSpace: "nowrap",
                                    fontSize: "0.65rem",
                                  }}
                                >
                                  {r.drug.drug_name}
                                </div>
                              </div>
                              <div
                                style={{
                                  fontSize: "0.62rem",
                                  color: due.overdue ? "#ef476f" : "var(--text-light)",
                                  fontWeight: due.overdue ? 700 : 400,
                                  whiteSpace: "nowrap",
                                  flexShrink: 0,
                                }}
                              >
                                {due.label}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    );
                  })
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
