import { useContext, useEffect, useState } from "react";
import { AuthContext } from "@/context/AuthContext";
import { getRTSHistory } from "@/api";
import type { ReturnToStock, PaginatedResponse } from "@/types";

const PAGE_SIZE = 20;

interface RTSHistViewProps {
  onBack: () => void;
  page?: number;
}

export default function RTSHistView({ onBack, page = 1 }: RTSHistViewProps) {
  const { token } = useContext(AuthContext);
  const [data, setData] = useState<PaginatedResponse<ReturnToStock>>({ items: [], total: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    const offset = (page - 1) * PAGE_SIZE;
    getRTSHistory(token, PAGE_SIZE, offset)
      .then((res) => setData(res as PaginatedResponse<ReturnToStock>))
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [token, page]);

  if (loading) return <p>Loading…</p>;
  if (error) return <p style={{ color: "var(--danger, #ff7675)" }}>{error}</p>;

  const { items, total } = data;
  const startIdx = (page - 1) * PAGE_SIZE;
  const endIdx = Math.min(startIdx + items.length, startIdx + PAGE_SIZE);

  return (
    <div className="vstack">
      <h2>Return to Stock History</h2>
      {items.length === 0 ? (
        <p style={{ color: "var(--text-light)" }}>No return-to-stock records found.</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>#</th>
              <th>RTS ID</th>
              <th>Refill #</th>
              <th>Drug</th>
              <th>NDC</th>
              <th>Qty Returned</th>
              <th>Returned By</th>
              <th>Date / Time</th>
            </tr>
          </thead>
          <tbody>
            {items.map((r, idx) => {
              const dt = new Date(r.returned_at);
              return (
                <tr key={r.id}>
                  <td><strong style={{ color: "var(--primary)" }}>{startIdx + idx + 1}</strong></td>
                  <td style={{ fontFamily: "monospace" }}>{r.id}</td>
                  <td style={{ fontFamily: "monospace" }}>{r.refill_id}</td>
                  <td>{r.drug.drug_name}</td>
                  <td style={{ fontFamily: "monospace", fontSize: "0.9rem" }}>{r.drug.ndc ?? "—"}</td>
                  <td style={{ fontWeight: 700, color: "var(--primary)" }}>{r.quantity}</td>
                  <td>{r.returned_by}</td>
                  <td style={{ fontFamily: "monospace", fontSize: "0.85rem" }}>
                    {dt.toLocaleDateString()} {dt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                  </td>
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
