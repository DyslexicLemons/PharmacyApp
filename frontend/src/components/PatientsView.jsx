import { useContext } from "react";
import { DataContext } from "@/context/DataContext";
const PAGE_SIZE = 15;

export default function PatientsView({ onBack, onSelectPatient, page = 1 }) {
  const { patients, loadingPatients, errorPatients } = useContext(DataContext);

  if (loadingPatients) return <p>Loading…</p>;
  if (errorPatients) return <p style={{ color: "#ff7675" }}>{errorPatients}</p>;

  const total = patients.length;
  const startIdx = (page - 1) * PAGE_SIZE;
  const endIdx = Math.min(startIdx + PAGE_SIZE, total);
  const pageItems = patients.slice(startIdx, endIdx);

  return (
    <div className="vstack">
      <h2>Patients</h2>
      <table className="table">
        <thead>
          <tr>
            <th>#</th>
            <th>LastName</th>
            <th>FirstName</th>
            <th>Date of Birth</th>
            <th>Address</th>
          </tr>
        </thead>
        <tbody>
          {pageItems.map((p, index) => (
            <tr
              key={p.id}
              onClick={() => onSelectPatient && onSelectPatient(p.id)}
              style={{ cursor: onSelectPatient ? "pointer" : "default" }}
              className={onSelectPatient ? "hover-row" : ""}
            >
              <td><strong style={{ color: "var(--primary)" }}>{startIdx + index + 1}</strong></td>
              <td>{p.last_name}</td>
              <td>{p.first_name}</td>
              <td>{new Date(p.dob).toLocaleDateString()}</td>
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
