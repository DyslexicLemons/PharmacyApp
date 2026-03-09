import { useContext, useEffect, useState } from "react";
import { AuthContext } from "@/context/AuthContext";
import { getDrugs } from "@/api";

const PAGE_SIZE = 15;

export default function DrugsView({ onBack, onSelectDrug, page = 1 }) {
  const { token } = useContext(AuthContext);
  const [data, setData] = useState({ items: [], total: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    const offset = (page - 1) * PAGE_SIZE;
    getDrugs(token, PAGE_SIZE, offset)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [token, page]);

  if (loading) return <p>Loading…</p>;
  if (error) return <p style={{ color: "#ff7675" }}>{error}</p>;

  const { items, total } = data;
  const startIdx = (page - 1) * PAGE_SIZE;
  const endIdx = Math.min(startIdx + items.length, startIdx + PAGE_SIZE);

  return (
    <div className="vstack">
      <h2>Drug Catalog</h2>
      <table className="table">
        <thead>
          <tr>
            <th>#</th>
            <th>Name</th>
            <th>Manufacturer</th>
            <th>Cost per Pill</th>
            <th>NIOSH</th>
          </tr>
        </thead>
        <tbody>
          {items.map((d, index) => (
            <tr
              key={d.id}
              onClick={() => onSelectDrug && onSelectDrug(d.id)}
              style={{ cursor: onSelectDrug ? "pointer" : "default" }}
              className={onSelectDrug ? "hover-row" : ""}
            >
              <td><strong style={{ color: "var(--primary)" }}>{startIdx + index + 1}</strong></td>
              <td>{d.drug_name}</td>
              <td>{d.manufacturer}</td>
              <td>{"$" + Number(d.cost).toFixed(2)}</td>
              <td>{d.niosh ? "✔️" : "—"}</td>
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
