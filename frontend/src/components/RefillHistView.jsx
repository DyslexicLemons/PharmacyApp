import { useContext } from "react";
import { DataContext } from "@/context/DataContext";

export default function RefillHistView() {
  const { refillHist, loadingRefillHist, errorRefillHist } = useContext(DataContext);

  if (loadingRefillHist) return <p>Loading…</p>;
  if (errorRefillHist) return <p style={{ color: "#ff7675" }}>{errorRefillHist}</p>;

  return (
    <div className="vstack">
      <h2>Refill History</h2>
      <table className="table">
        <thead>
          <tr>
            <th>Patient</th>
            <th>Drug</th>
            <th>Quantity</th>
            <th>Days Supply</th>
            <th>Completed Date</th>
            <th>Sold Date</th>
          </tr>
        </thead>
        <tbody>
          {refillHist.map((s) => (
            <tr key={s.id}>
              <td>{s.patient?.first_name} {s.patient?.last_name}</td>
              <td>{s.drug?.drug_name}</td>
              <td>{s.quantity}</td>
              <td>{s.days_supply}</td>
              <td>{s.completed_date ? new Date(s.completed_date).toLocaleDateString() : "—"}</td>
              <td>{s.sold_date ? new Date(s.sold_date).toLocaleDateString() : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
