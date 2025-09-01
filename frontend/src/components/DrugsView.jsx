import { useContext } from "react";
import { DataContext } from "@/context/DataContext";

export default function DrugsView() {
  const { drugs, loadingDrugs, errorDrugs } = useContext(DataContext);

  if (loadingDrugs) return <p>Loading…</p>;
  if (errorDrugs) return <p style={{ color: "#ff7675" }}>{errorDrugs}</p>;

  return (
    <div className="vstack">
      <h2>Drug Catalog</h2>
      <table className="table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Name</th>
            <th>Manufacturer</th>
            <th>Cost per Pill</th>
            <th>NIOSH</th>
          </tr>
        </thead>
        <tbody>
          {drugs.map((d) => (
            <tr key={d.id}>
              <td>{d.id}</td>
              <td>{d.drug_name}</td>
              <td>{d.manufacturer}</td>
              <td>{"$" + d.cost}</td>
              <td>{d.niosh ? "✔️" : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
