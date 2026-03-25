import { useContext, useEffect, useState } from "react";
import { AuthContext } from "@/context/AuthContext";
import { getStock } from "@/api";
import type { StockEntry, PaginatedResponse } from "@/types";

const PAGE_SIZE = 15;

interface StockViewProps {
  onBack?: () => void;
  onSelectStock?: (drugId: number) => void;
  page?: number;
  onTotalPages?: (n: number) => void;
}

export default function StockView({ onBack, onSelectStock, page = 1, onTotalPages }: StockViewProps) {
  const { token } = useContext(AuthContext);
  const [data, setData] = useState<PaginatedResponse<StockEntry>>({ items: [], total: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    const offset = (page - 1) * PAGE_SIZE;
    getStock(token, PAGE_SIZE, offset)
      .then((res) => setData(Array.isArray(res) ? { items: res, total: res.length } : res))
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [token, page]);

  if (loading) return <p>Loading…</p>;
  if (error) return <p style={{ color: "#ff7675" }}>{error}</p>;

  const { items, total } = data;
  const startIdx = (page - 1) * PAGE_SIZE;
  const endIdx = Math.min(startIdx + items.length, startIdx + PAGE_SIZE);

  useEffect(() => {
    onTotalPages?.(Math.ceil(total / PAGE_SIZE) || 1);
  }, [total, onTotalPages]);

  return (
    <div className="vstack">
      <h2>Drug Stock</h2>
      <table className="table">
        <thead>
          <tr>
            <th>#</th>
            <th>Name</th>
            <th>NDC</th>
            <th>Manufacturer</th>
            <th>Quantity</th>
            <th>Full Containers</th>
            <th>Partial Container</th>
            <th>RTS Count</th>
            <th>RTS Units</th>
            <th>NIOSH</th>
          </tr>
        </thead>
        <tbody>
          {items.map((s, index) => (
            <tr
              key={s.drug_id}
              onClick={() => onSelectStock && onSelectStock(s.drug_id)}
              style={{ cursor: onSelectStock ? "pointer" : "default" }}
              className={onSelectStock ? "hover-row" : ""}
            >
              <td><strong style={{ color: "var(--primary)" }}>{startIdx + index + 1}</strong></td>
              <td>{s.drug.drug_name}</td>
              <td style={{ fontFamily: "monospace", fontSize: "0.9rem" }}>{s.drug.ndc ?? "—"}</td>
              <td>{s.drug.manufacturer}</td>
              <td>{s.quantity}</td>
              <td>{Math.floor(s.quantity / s.package_size)}</td>
              <td>{s.quantity % s.package_size > 0 ? `${s.quantity % s.package_size} / ${s.package_size}` : "—"}</td>
              <td style={{ fontFamily: "monospace" }}>
                {s.rts_count > 0 ? (
                  <span style={{ color: "var(--warning, #ffbe0b)" }}>{s.rts_count}</span>
                ) : "—"}
              </td>
              <td style={{ fontFamily: "monospace" }}>
                {s.rts_quantity > 0 ? (
                  <span style={{ color: "var(--warning, #ffbe0b)" }}>{s.rts_quantity}</span>
                ) : "—"}
              </td>
              <td>{s.drug.niosh ? "✔️" : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
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
