import { useContext } from "react";
import { DataContext } from "@/context/DataContext";

export default function StockView() {
  const {  stock, loadingStock, errorStock } = useContext(DataContext);

  if (loadingStock) return <p>Loading…</p>;
  if (errorStock) return <p style={{ color: "#ff7675" }}>{errorStock}</p>;

  return (
    <div className="vstack">
      <h2>Drug Stock</h2>
      <table className="table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Name</th>
            <th>Manufacturer</th>
            <th>Quantity</th>
            <th>NIOSH</th>
          </tr>
        </thead>
        <tbody>
            {stock.map((s) => (
            <tr key={s.drug_id}>
                <td>{s.drug_id}</td>
                <td>{s.drug.drug_name}</td>
                <td>{s.drug.manufacturer}</td>
                <td>{s.quantity}</td>
                <td>{s.drug.niosh ? "✔️" : "—"}</td>
            </tr>
            ))}
        </tbody>
      </table>
    </div>
  );
}
