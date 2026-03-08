import { useContext } from "react";
import { DataContext } from "@/context/DataContext";
const PAGE_SIZE = 15;

export default function StockView({ onBack, onSelectStock, page = 1 }) {
  const {  stock, loadingStock, errorStock } = useContext(DataContext);

  if (loadingStock) return <p>Loading…</p>;
  if (errorStock) return <p style={{ color: "#ff7675" }}>{errorStock}</p>;

  const total = stock.length;
  const startIdx = (page - 1) * PAGE_SIZE;
  const endIdx = Math.min(startIdx + PAGE_SIZE, total);
  const pageItems = stock.slice(startIdx, endIdx);

  return (
    <div className="vstack">
      <h2>Drug Stock</h2>
      <table className="table">
        <thead>
          <tr>
            <th>#</th>
            <th>Name</th>
            <th>Manufacturer</th>
            <th>Quantity</th>
            <th>NIOSH</th>
          </tr>
        </thead>
        <tbody>
            {pageItems.map((s, index) => (
            <tr
              key={s.drug_id}
              onClick={() => onSelectStock && onSelectStock(s.drug_id)}
              style={{ cursor: onSelectStock ? "pointer" : "default" }}
              className={onSelectStock ? "hover-row" : ""}
            >
                <td><strong style={{ color: "var(--primary)" }}>{startIdx + index + 1}</strong></td>
                <td>{s.drug.drug_name}</td>
                <td>{s.drug.manufacturer}</td>
                <td>{s.quantity}</td>
                <td>{s.drug.niosh ? "✔️" : "—"}</td>
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
