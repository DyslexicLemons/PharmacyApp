import { useContext, useEffect, useState } from "react";
import { AuthContext } from "@/context/AuthContext";
import { getShipments } from "@/api";
import type { Shipment, PaginatedResponse } from "@/types";

const PAGE_SIZE = 15;

interface ShipmentItemDetail {
  id: number;
  drug: { drug_name: string; manufacturer: string };
  bottles_received: number;
  units_per_bottle: number;
}

interface ShipmentWithDetails extends Shipment {
  performed_at: string;
  performed_by: string;
  items: ShipmentItemDetail[];
}

interface ShipmentHistViewProps {
  onBack?: () => void;
  page?: number;
  onTotalPages?: (n: number) => void;
}

export default function ShipmentHistView({ onBack, page = 1, onTotalPages }: ShipmentHistViewProps) {
  const { token } = useContext(AuthContext);
  const [data, setData] = useState<PaginatedResponse<ShipmentWithDetails>>({ items: [], total: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    const offset = (page - 1) * PAGE_SIZE;
    getShipments(token, PAGE_SIZE, offset)
      .then((res) => setData(Array.isArray(res) ? { items: res as ShipmentWithDetails[], total: res.length } : res as PaginatedResponse<ShipmentWithDetails>))
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [token, page]);

  function toggleExpand(id: number) {
    setExpanded((prev) => ({ ...prev, [id]: !prev[id] }));
  }

  useEffect(() => {
    onTotalPages?.(Math.ceil(data.total / PAGE_SIZE) || 1);
  }, [data.total, onTotalPages]);

  if (loading) return <p>Loading…</p>;
  if (error) return <p style={{ color: "var(--danger)" }}>{error}</p>;

  const { items, total } = data;
  const startIdx = (page - 1) * PAGE_SIZE;
  const endIdx = Math.min(startIdx + items.length, startIdx + PAGE_SIZE);

  return (
    <div className="vstack">
      <h2>Inventory Shipment History</h2>

      {items.length === 0 ? (
        <p style={{ color: "var(--text-light)" }}>No shipments recorded yet.</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>#</th>
              <th>Shipment ID</th>
              <th>Date / Time</th>
              <th>Performed By</th>
              <th>Drugs</th>
              <th>Total Bottles</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {items.map((s, index) => {
              const totalBottles = s.items.reduce((sum, i) => sum + i.bottles_received, 0);
              const isOpen = !!expanded[s.id];
              return [
                <tr
                  key={s.id}
                  style={{ cursor: "pointer" }}
                  className="hover-row"
                  onClick={() => toggleExpand(s.id)}
                >
                  <td><strong style={{ color: "var(--primary)" }}>{startIdx + index + 1}</strong></td>
                  <td>#{s.id}</td>
                  <td>{new Date(s.performed_at).toLocaleString()}</td>
                  <td>{s.performed_by}</td>
                  <td>{s.items.length}</td>
                  <td>{totalBottles}</td>
                  <td style={{ color: "var(--text-light)", fontSize: "0.85rem" }}>
                    {isOpen ? "▲ collapse" : "▼ details"}
                  </td>
                </tr>,
                isOpen && (
                  <tr key={`${s.id}-detail`}>
                    <td colSpan={7} style={{ padding: "0.5rem 1rem 1rem 2rem", background: "rgba(255,255,255,0.03)" }}>
                      <table className="table" style={{ margin: 0 }}>
                        <thead>
                          <tr>
                            <th>Drug</th>
                            <th>Manufacturer</th>
                            <th>Bottles Received</th>
                            <th>Units / Bottle</th>
                            <th>Total Units Added</th>
                          </tr>
                        </thead>
                        <tbody>
                          {s.items.map((item) => (
                            <tr key={item.id}>
                              <td>{item.drug.drug_name}</td>
                              <td>{item.drug.manufacturer}</td>
                              <td>{item.bottles_received}</td>
                              <td>{item.units_per_bottle}</td>
                              <td>{item.bottles_received * item.units_per_bottle}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </td>
                  </tr>
                ),
              ];
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
