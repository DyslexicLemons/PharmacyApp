import React, { useEffect, useState } from "react";
import {getPatient } from "@/api";
import Badge from "@/components/Badge"

export default function PatientProfile({ pid }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let mounted = true;
    getPatient(pid)
      .then((d) => mounted && setData(d))
      .catch((e) => setError(e.message));
    return () => {
      mounted = false;
    };
  }, [pid]);

  if (error) return <p style={{ color: "#ff7675" }}>{error}</p>;
  if (!data) return <p>Loading…</p>;

  return (
    <div className="vstack">
      <h2>Patient Profile</h2>
      <div className="card vstack">
        <div className="hstack" style={{ justifyContent: "space-between" }}>
          <strong>
            {data.last_name}, {data.first_name}
          </strong>
          <span>DOB: {new Date(data.dob).toLocaleDateString()}</span>
        </div>
        <div>{data.address}</div>
      </div>
      <h3>Prescriptions</h3>
      <table className="table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Drug</th>
            <th>Quantity Remaining</th>
            <th>Date Received</th>
          </tr>
        </thead>
        <tbody>
          {data.prescriptions.map((r) => (
            <tr key={r.id}>
              <td>{r.id}</td>
              <td>{r.drug_name}</td>
              <td>{r.remaining_quantity}</td>
              <td>{new Date(r.date_received).toLocaleDateString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}