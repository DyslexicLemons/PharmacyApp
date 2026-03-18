import { useContext, useEffect, useState } from "react";
import { AuthContext } from "@/context/AuthContext";
import { getPrescribers } from "@/api";
import type { Prescriber, PaginatedResponse } from "@/types";

const PAGE_SIZE = 15;

interface PrescribersViewProps {
  onBack?: () => void;
  onSelectPrescriber?: (id: number) => void;
  page?: number;
}

export default function PrescribersView({ onBack, onSelectPrescriber, page = 1 }: PrescribersViewProps) {
  const { token } = useContext(AuthContext);
  const [data, setData] = useState<PaginatedResponse<Prescriber>>({ items: [], total: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    const offset = (page - 1) * PAGE_SIZE;
    getPrescribers(token, PAGE_SIZE, offset)
      .then(setData)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [token, page]);

  if (loading) return <p>Loading…</p>;
  if (error) return <p style={{ color: "#ff7675" }}>{error}</p>;

  const { items, total } = data;
  const startIdx = (page - 1) * PAGE_SIZE;
  const endIdx = Math.min(startIdx + items.length, startIdx + PAGE_SIZE);

  return (
    <div className="vstack">
      <h2>Prescribers</h2>
      <table className="table">
        <thead>
          <tr>
            <th>#</th>
            <th>NPI</th>
            <th>LastName</th>
            <th>FirstName</th>
            <th>Phone Number</th>
            <th>Address</th>
          </tr>
        </thead>
        <tbody>
          {items.map((p, index) => (
            <tr
              key={p.id}
              onClick={() => onSelectPrescriber && onSelectPrescriber(p.id)}
              style={{ cursor: onSelectPrescriber ? "pointer" : "default" }}
              className={onSelectPrescriber ? "hover-row" : ""}
            >
              <td><strong style={{ color: "var(--primary)" }}>{startIdx + index + 1}</strong></td>
              <td>{p.npi}</td>
              <td>{p.last_name}</td>
              <td>{p.first_name}</td>
              <td>{p.phone_number}</td>
              <td>{p.address}</td>
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
