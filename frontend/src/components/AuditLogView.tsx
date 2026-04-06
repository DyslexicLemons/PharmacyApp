import { useContext, useEffect, useState } from "react";
import { AuthContext } from "@/context/AuthContext";
import { getAuditLog } from "@/api";
import type { AuditLogEntry, PaginatedResponse } from "@/types";

const PAGE_SIZE = 15;

interface AuditFilters {
  username?: string;
  prescriptionId?: number;
}

interface AuditLogViewProps {
  onBack?: () => void;
  page?: number;
  onTotalPages?: (n: number) => void;
}

export default function AuditLogView({ onBack, page = 1, onTotalPages }: AuditLogViewProps) {
  const { token } = useContext(AuthContext);
  const [data, setData] = useState<PaginatedResponse<AuditLogEntry>>({ items: [], total: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [usernameInput, setUsernameInput] = useState("");
  const [rxInput, setRxInput] = useState("");
  const [filters, setFilters] = useState<AuditFilters>({});

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    const offset = (page - 1) * PAGE_SIZE;
    getAuditLog(token, PAGE_SIZE, offset, filters)
      .then((res) => setData(Array.isArray(res) ? { items: res, total: res.length } : res))
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [token, page, filters]);

  function applyFilters(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const next: AuditFilters = {};
    if (usernameInput.trim()) next.username = usernameInput.trim();
    const rxNum = parseInt(rxInput.trim(), 10);
    if (rxInput.trim() && !isNaN(rxNum)) next.prescriptionId = rxNum;
    setFilters(next);
  }

  function clearFilters() {
    setUsernameInput("");
    setRxInput("");
    setFilters({});
  }

  const hasFilters = Object.keys(filters).length > 0;

  useEffect(() => {
    onTotalPages?.(Math.ceil(data.total / PAGE_SIZE) || 1);
  }, [data.total, onTotalPages]);

  if (error) return <p style={{ color: "#ff7675" }}>{error}</p>;

  const { items, total } = data;
  const startIdx = (page - 1) * PAGE_SIZE;
  const endIdx = Math.min(startIdx + items.length, startIdx + PAGE_SIZE);

  return (
    <div className="vstack">
      <h2>Audit Log</h2>

      <form
        onSubmit={applyFilters}
        style={{ display: "flex", gap: "0.5rem", alignItems: "flex-end", flexWrap: "wrap", marginBottom: "0.75rem" }}
      >
        <div className="vstack" style={{ gap: "0.25rem" }}>
          <label style={{ fontSize: "0.8rem", color: "var(--text-light)" }}>Username</label>
          <input
            className="input"
            value={usernameInput}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setUsernameInput(e.target.value)}
            placeholder="e.g. jsmith"
            style={{ width: "160px" }}
          />
        </div>
        <div className="vstack" style={{ gap: "0.25rem" }}>
          <label style={{ fontSize: "0.8rem", color: "var(--text-light)" }}>RX #</label>
          <input
            className="input"
            value={rxInput}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setRxInput(e.target.value)}
            placeholder="e.g. 42"
            type="number"
            min="1"
            style={{ width: "100px" }}
          />
        </div>
        <button className="btn" type="submit">Filter</button>
        {hasFilters && (
          <button className="btn btn-secondary" type="button" onClick={clearFilters}>
            Clear
          </button>
        )}
      </form>

      {hasFilters && (
        <p style={{ fontSize: "0.85rem", color: "var(--text-light)", marginBottom: "0.5rem" }}>
          Filtering by:{" "}
          {filters.username && <strong>user "{filters.username}"</strong>}
          {filters.username && filters.prescriptionId != null && " and "}
          {filters.prescriptionId != null && <strong>RX #{filters.prescriptionId}</strong>}
        </p>
      )}

      {loading ? (
        <p>Loading…</p>
      ) : items.length === 0 ? (
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
                  <td>{(entry as AuditLogEntry & { performed_by?: string }).performed_by ?? "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}

      {total > 0 && (
        <div style={{ color: "var(--text-light)", fontSize: "0.9rem", marginTop: "0.5rem" }}>
          Showing {startIdx + 1}–{endIdx} of {total}
          {page > 1 && <span> | [p] prev</span>}
          {endIdx < total && <span> | [n] next</span>}
        </div>
      )}
    </div>
  );
}
