import { useContext } from "react";
import { DataContext } from "@/context/DataContext";
const PAGE_SIZE = 15;

export default function RefillHistView({ onBack, page = 1 }) {
  const { refillHist, loadingRefillHist, errorRefillHist } = useContext(DataContext);

  if (loadingRefillHist) return <p>Loading…</p>;
  if (errorRefillHist) return <p style={{ color: "#ff7675" }}>{errorRefillHist}</p>;

  // Compute per-prescription fill number (sorted by id so oldest fill = #1)
  const fillNumberMap = {};
  const rxCounter = {};
  [...refillHist].sort((a, b) => a.id - b.id).forEach((r) => {
    const rxId = r.prescription?.id;
    rxCounter[rxId] = (rxCounter[rxId] || 0) + 1;
    fillNumberMap[r.id] = rxCounter[rxId];
  });

  const total = refillHist.length;
  const startIdx = (page - 1) * PAGE_SIZE;
  const endIdx = Math.min(startIdx + PAGE_SIZE, total);
  const pageItems = refillHist.slice(startIdx, endIdx);

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
            <th>cost</th>
            <th>Insurance</th>
            <th>Completed Date</th>
            <th>Sold Date</th>
          </tr>
        </thead>
        <tbody>
          {pageItems.map((s, index) => (
            <tr key={s.id}>
              <td><strong style={{ color: "var(--primary)" }}>{fillNumberMap[s.id]}</strong></td>
              <td><strong>{s.prescription?.id}</strong></td>
              <td>{s.patient?.first_name} {s.patient?.last_name}</td>
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
