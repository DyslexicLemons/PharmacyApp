import { useContext, useEffect, useState } from "react";
import { AuthContext } from "@/context/AuthContext";
import { getRefillHist } from "@/api";
import type { Refill, PaginatedResponse } from "@/types";

const PAGE_SIZE = 15;

interface RefillHistViewProps {
  onBack?: () => void;
  page?: number;
}

export default function RefillHistView({ onBack, page = 1 }: RefillHistViewProps) {
  const { token } = useContext(AuthContext);
  const [data, setData] = useState<PaginatedResponse<Refill & { completed_date?: string | null; sold_date?: string | null; insurance?: { insurance_company?: { plan_name?: string } } | null }>>({ items: [], total: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    const offset = (page - 1) * PAGE_SIZE;
    getRefillHist(token, PAGE_SIZE, offset)
      .then((res) => setData(Array.isArray(res) ? { items: res as typeof data.items, total: res.length } : res as typeof data))
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [token, page]);

  if (loading) return <p>Loading…</p>;
  if (error) return <p style={{ color: "#ff7675" }}>{error}</p>;

  const { items, total } = data;
  const startIdx = (page - 1) * PAGE_SIZE;
  const endIdx = Math.min(startIdx + items.length, startIdx + PAGE_SIZE);

  // Compute per-prescription fill number within the current page
  const fillNumberMap: Record<number, number> = {};
  const rxCounter: Record<number, number> = {};
  [...items].sort((a, b) => a.id - b.id).forEach((r) => {
    const rxId = r.prescription?.id;
    if (rxId != null) {
      rxCounter[rxId] = (rxCounter[rxId] || 0) + 1;
      fillNumberMap[r.id] = rxCounter[rxId];
    }
  });

  return (
    <div className="vstack">
      <h2>Refill History</h2>
      <table className="table">
        <thead>
          <tr>
            <th>Fill #</th>
            <th>Rx #</th>
            <th>Patient</th>
            <th>Drug</th>
            <th>Quantity</th>
            <th>Days Supply</th>
            <th>Cost</th>
            <th>Insurance</th>
            <th>Completed Date</th>
            <th>Sold Date</th>
          </tr>
        </thead>
        <tbody>
          {items.map((s) => (
            <tr key={s.id}>
              <td><strong style={{ color: "var(--primary)" }}>{fillNumberMap[s.id]}</strong></td>
              <td><strong>{s.prescription?.id}</strong></td>
              <td>{s.patient?.first_name?.toUpperCase()} {s.patient?.last_name?.toUpperCase()}</td>
              <td>{s.drug?.drug_name}</td>
              <td>{s.quantity}</td>
              <td>{s.days_supply}</td>
              <td>{"$" + Number(s.total_cost).toFixed(2)}</td>
              <td>{s.insurance?.insurance_company?.plan_name ?? "—"}</td>
              <td>{s.completed_date ? new Date(s.completed_date).toLocaleDateString() : "—"}</td>
              <td>{s.sold_date ? new Date(s.sold_date).toLocaleDateString() : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
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
