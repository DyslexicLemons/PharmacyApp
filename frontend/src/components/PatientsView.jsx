import { useContext } from "react";
import { DataContext } from "@/context/DataContext"; 

export default function PatientsView() {
  const { patients, loadingPatients, errorPatients } = useContext(DataContext);

  if (loadingPatients) return <p>Loading…</p>;
  if (errorPatients) return <p style={{ color: "#ff7675" }}>{errorPatients}</p>;

  return (
    <div className="vstack">
      <h2>Patients</h2>
      <table className="table">
        <thead>
          <tr>
            <th>ID</th>
            <th>LastName</th>
            <th>FirstName</th>
            <th>Date of Birth</th>
            <th>Address</th>
          </tr>
        </thead>
        <tbody>
          {patients.map((p) => (
            <tr key={p.id}>
              <td>{p.id}</td>
              <td>{p.last_name}</td>
              <td>{p.first_name}</td>
              <td>{new Date(p.dob).toLocaleDateString()}</td>
              <td>{p.address}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
