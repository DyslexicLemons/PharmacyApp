import { useContext, useEffect, useState } from "react";
import { AuthContext } from "@/context/AuthContext";
import { getAuditLog } from "@/api";

const PAGE_SIZE = 15;

export default function AuditLogView({ onBack, page = 1 }) {
  const { token } = useContext(AuthContext);
  const [data, setData] = useState({ items: [], total: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    const offset = (page - 1) * PAGE_SIZE;
    getAuditLog(token, PAGE_SIZE, offset)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [token, page]);

  if (loading) return <p>Loading…</p>;
  if (error) return <p style={{ color: "#ff7675" }}>{error}</p>;

  const { items, total } = data;
  const startIdx = (page - 1) * PAGE_SIZE;
  const endIdx = Math.min(startIdx + items.length, startIdx + PAGE_SIZE);

  return (
    <div className="vstack">
      <h2>Audit Log</h2>
      {items.length === 0 ? (
        <p style={{ color: "var(--text-light)" }}>No audit entries found.</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>#</th>
              <th>Timestamp</th>
              <th>Action</th>
              <th>Entity</th>
              <th>Entity ID</th>
              <th>RX#</th>
              <th>Details</th>
              <th>User</th>
            </tr>
          </thead>
          <tbody>
            {items.map((entry, index) => {
              const rxNum = entry.prescription_id ?? (entry.entity_type === "prescription" ? entry.entity_id : null);
              return (
              <tr key={entry.id}>
                <td><strong style={{ color: "var(--primary)" }}>{startIdx + index + 1}</strong></td>
                <td style={{ fontSize: "0.85rem", whiteSpace: "nowrap" }}>
                  {new Date(entry.timestamp).toLocaleString()}
                </td>
                <td>
                  <span style={{
                    padding: "2px 8px",
                    borderRadius: "4px",
                    fontSize: "0.8rem",
                    fontWeight: 600,
                    background: "var(--bg-light)",
                    fontFamily: "monospace",
                  }}>
                    {entry.action}
                  </span>
                </td>
                <td>{entry.entity_type ?? "—"}</td>
                <td>{entry.entity_id ?? "—"}</td>
                <td>{rxNum != null ? <strong style={{ color: "var(--primary)" }}>#{rxNum}</strong> : "—"}</td>
                <td style={{ fontSize: "0.85rem", maxWidth: "300px", wordBreak: "break-word" }}>
                  {entry.details ?? "—"}
                </td>
                <td>{entry.performed_by ?? "—"}</td>
              </tr>
              );
            })}
          </tbody>
        </table>
      )}
      {total > PAGE_SIZE && (
        <div style={{ color: "var(--text-light)", fontSize: "0.9rem", marginTop: "0.5rem" }}>
          Showing {startIdx + 1}–{endIdx} of {total}
          {page > 1 && <span> | [p] prev</span>}
          {endIdx < total && <span> | [n] next</span>}
        </div>
      )}
    </div>
  );
}
