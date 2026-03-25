import { useContext, useEffect, useState } from "react";
import { AuthContext } from "@/context/AuthContext";
import { getPatients } from "@/api";
import type { PatientSearchResult, PaginatedResponse } from "@/types";

const PAGE_SIZE = 15;

interface PatientsViewProps {
  onBack?: () => void;
  onSelectPatient?: (id: number) => void;
  page?: number;
  onTotalPages?: (n: number) => void;
}

export default function PatientsView({ onBack, onSelectPatient, page = 1, onTotalPages }: PatientsViewProps) {
  const { token } = useContext(AuthContext);
  const [data, setData] = useState<PaginatedResponse<PatientSearchResult>>({ items: [], total: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    const offset = (page - 1) * PAGE_SIZE;
    getPatients(token, PAGE_SIZE, offset)
      .then(setData)
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
      <h2>Patients</h2>
      <table className="table">
        <thead>
          <tr>
            <th>#</th>
            <th>Last Name</th>
            <th>First Name</th>
          </tr>
        </thead>
        <tbody>
          {items.map((p, index) => (
            <tr
              key={p.id}
              onClick={() => onSelectPatient && onSelectPatient(p.id)}
              style={{ cursor: onSelectPatient ? "pointer" : "default" }}
              className={onSelectPatient ? "hover-row" : ""}
            >
              <td><strong style={{ color: "var(--primary)" }}>{startIdx + index + 1}</strong></td>
              <td>{p.last_name.toUpperCase()}</td>
              <td>{p.first_name.toUpperCase()}</td>
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
