import React, { useEffect, useState } from "react";
import { advanceRx, fetchQueue, getPatient, searchPatients } from "./api";

const NEXT = { QT: "QV1", QV1: "QP", QP: "QV2", QV2: "DONE" };

function Badge({ state }) {
  return <span className={`badge state-${state}`}>{state}</span>;
}

function CommandBar({ onSubmit }) {
  const [cmd, setCmd] = useState("");
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit(cmd.trim());
        setCmd("");
      }}
      className="hstack"
    >
      <input
        className="input"
        placeholder="Type command: qt | qp | qv1 | qv2 | all | lastname,firstname"
        value={cmd}
        onChange={(e) => setCmd(e.target.value)}
      />
      <button className="btn" type="submit">
        Go
      </button>
    </form>
  );
}

function Home({ onCommand }) {
  return (
    <div className="vstack">
      <h1>🏥 Pharmacy Console</h1>
      <p>Type a command to navigate queues or open a patient profile.</p>
      <ul>
        <li>
          <code>qt</code> – Queue Triage
        </li>
        <li>
          <code>qv1</code> – Verify 1
        </li>
        <li>
          <code>qp</code> – Prep/Fill
        </li>
        <li>
          <code>qv2</code> – Final Verify
        </li>
        <li>
          <code>all</code> – All active prescriptions
        </li>
        <li>
          <code>lastname,firstname</code> – Open patient profile (e.g.,{" "}
          <code>smith,john</code>)
        </li>
      </ul>
      <CommandBar onSubmit={onCommand} />
    </div>
  );
}

function QueueView({ stateFilter }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    fetchQueue(stateFilter && stateFilter !== "ALL" ? stateFilter : undefined)
      .then((data) => {
        if (mounted) {
          setRows(data);
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
      setRows((prev) => prev.map((r) => (r.id === id ? updated : r)));
    } catch (e) {
      alert(e.message);
    }
  }

  return (
    <div className="vstack">
      <h2>
        {stateFilter === "ALL" ? "All Prescriptions" : `Queue: ${stateFilter}`}
      </h2>
      {loading ? (
        <p>Loading…</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Drug</th>
              <th>Patient ID</th>
              <th>Qty</th>
              <th>Due</th>
              <th>Priority</th>
              <th>State</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td>{r.id}</td>
                <td>{r.drug_name}</td>
                <td>{r.patient_id}</td>
                <td>{r.quantity}</td>
                <td>{new Date(r.due_date).toLocaleDateString()}</td>
                <td>{r.priority}</td>
                <td>
                  <Badge state={r.state} />
                </td>
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

function PatientProfile({ pid }) {
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
            <th>Qty</th>
            <th>Due</th>
            <th>Priority</th>
            <th>State</th>
          </tr>
        </thead>
        <tbody>
          {data.prescriptions.map((r) => (
            <tr key={r.id}>
              <td>{r.id}</td>
              <td>{r.drug_name}</td>
              <td>{r.quantity}</td>
              <td>{new Date(r.due_date).toLocaleDateString()}</td>
              <td>{r.priority}</td>
              <td>
                <Badge state={r.state} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function App() {
  const [route, setRoute] = useState({ view: "HOME" });

  function handleCommand(input) {
    const cmd = input.toLowerCase();
    if (["qt", "qv1", "qp", "qv2"].includes(cmd)) {
      setRoute({ view: "QUEUE", state: cmd.toUpperCase() });
      return;
    }
    if (cmd === "all") {
      setRoute({ view: "QUEUE", state: "ALL" });
      return;
    }
    if (cmd.includes(",")) {
      searchPatients(input)
        .then((list) => {
          if (list.length === 0) {
            alert("No matching patients");
          } else if (list.length === 1) {
            setRoute({ view: "PATIENT", pid: list[0].id });
          } else {
            const names = list
              .map((p) => `${p.id}: ${p.last_name}, ${p.first_name}`)
              .join("\n");
            const pick = prompt(
              `Multiple matches. Enter ID to open:\n${names}`
            );
            const chosen = list.find((p) => String(p.id) === String(pick));
            if (chosen) setRoute({ view: "PATIENT", pid: chosen.id });
          }
        })
        .catch((e) => alert(e.message));
      return;
    }
    alert("Unknown command");
  }

  return (
    <div className="container vstack">
      <div className="card vstack">
        <CommandBar onSubmit={handleCommand} />
        {route.view === "HOME" && <Home onCommand={handleCommand} />}
        {route.view === "QUEUE" && <QueueView stateFilter={route.state} />}
        {route.view === "PATIENT" && <PatientProfile pid={route.pid} />}
      </div>
      <footer>
        API: {import.meta.env.VITE_API_BASE || "http://localhost:8000"}
      </footer>
    </div>
  );
}
