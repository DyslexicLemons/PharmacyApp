import { useContext } from "react";
import { DataContext } from "@/context/DataContext";
const PAGE_SIZE = 15;

export default function PrescribersView({ onBack, onSelectPrescriber, page = 1 }) {
  const { prescribers, loadingPrescribers, errorPrescribers } = useContext(DataContext);

  if (loadingPrescribers) return <p>Loading…</p>;
  if (errorPrescribers) return <p style={{ color: "#ff7675" }}>{errorPrescribers}</p>;

  const total = prescribers.length;
  const startIdx = (page - 1) * PAGE_SIZE;
  const endIdx = Math.min(startIdx + PAGE_SIZE, total);
  const pageItems = prescribers.slice(startIdx, endIdx);

  return (
    <div className="vstack">
      <h2>Presribers</h2>
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
          {pageItems.map((p, index) => (
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