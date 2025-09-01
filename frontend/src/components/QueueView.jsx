import React, { useEffect, useState } from "react";
import Badge from "@/components/Badge"; // Badge component
import { advanceRx, fetchQueue } from "@/api"; // API functions


const NEXT = { QT: "QV1", QV1: "QP", QP: "QV2", QV2: "DONE" };

export default function QueueView({ stateFilter }) {
  const [refills, setRefills] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    fetchQueue(stateFilter && stateFilter !== "ALL" ? stateFilter : undefined)
      .then((data) => {
        if (mounted) {
          setRefills(data);
          setError("");
        }
      })
      .catch((err) => setError(err.message))
      .finally(() => mounted && setLoading(false));
    return () => {
      mounted = false;
    };
  }, [stateFilter]);

  async function handleAdvance(id) {
    try {
      const updated = await advanceRx(id);
      setRefills((prev) => prev.map((r) => (r.id === id ? updated : r)));
    } catch (e) {
      alert(e.message);
    }
  }

  return (
    <div className="vstack">
      <h2>{stateFilter === "ALL" ? "All Refills" : `Queue: ${stateFilter}`}</h2>
      {loading ? (
        <p>Loading…</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Drug</th>
              <th>Patient</th>
              <th>Qty</th>
              <th>Days Supply</th>
              <th>Due</th>
              <th>Priority</th>
              <th>State</th>
              <th>Action</th>
            </tr>
          </thead>
            <tbody>
              {refills.map((r) => (
                <tr key={r.id}>
                  <td>{r.id}</td>
                  <td>{r.drug.drug_name}</td>
                  <td>{r.patient.first_name} {r.patient.last_name}</td>
                  <td>{r.quantity}</td>
                  <td>{r.days_supply}</td>
                  <td>{new Date(r.due_date).toLocaleDateString()}</td>
                  <td>{r.priority}</td>
                  <td><Badge state={r.state} /></td>
                  <td>
                    {r.state in NEXT ? (
                      <button className="btn" onClick={() => handleAdvance(r.id)}>
                        Move → {NEXT[r.state]}
                      </button>
                    ) : (
                      <span className="badge state-DONE">DONE</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
        </table>
      )}
      {error && <p style={{ color: "#ff7675" }}>{error}</p>}
    </div>
  );
}
