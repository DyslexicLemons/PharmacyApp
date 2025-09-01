import { useContext } from "react";
import { DataContext } from "@/context/DataContext"; 

export default function PrescribersView() {
  const { prescribers, loadingPrescribers, errorPrescribers } = useContext(DataContext);

  if (loadingPrescribers) return <p>Loading…</p>;
  if (errorPrescribers) return <p style={{ color: "#ff7675" }}>{errorPrescribers}</p>;

  return (
    <div className="vstack">
      <h2>Presribers</h2>
      <table className="table">
        <thead>
          <tr>
            <th>ID</th>
            <th>NPI</th>
            <th>LastName</th>
            <th>FirstName</th>
            <th>Phone Number</th>
            <th>Address</th>
          </tr>
        </thead>
        <tbody>
          {prescribers.map((p) => (
            <tr key={p.id}>
              <td>{p.id}</td>
              <td>{p.npi}</td>
              <td>{p.last_name}</td>
              <td>{p.first_name}</td>
              <td>{p.phone_number}</td>
              <td>{p.address}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}