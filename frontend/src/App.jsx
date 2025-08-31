import React, { useState } from "react";

import { advanceRx, fetchQueue, getDrugs, getPatients, searchPatients } from "@/api";

import PatientProfile from "@/components/PatientProfile";
import DrugsView from "@/components/DrugsView";
import PatientsView from "@/components/PatientsView";
import QueueView from "@/components/QueueView";
import Home from "@/components/Home";
import CommandBar from "@/components/CommandBar";

const NEXT = { QT: "QV1", QV1: "QP", QP: "QV2", QV2: "DONE" };

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
            const pick = prompt(`Multiple matches. Enter ID to open:\n${names}`);
            const chosen = list.find((p) => String(p.id) === String(pick));
            if (chosen) setRoute({ view: "PATIENT", pid: chosen.id });
          }
        })
        .catch((e) => alert(e.message));
      return;
    }
    if (cmd === "drugs") setRoute({ view: "DRUGS" });
    else if (cmd === "patients") setRoute({ view: "PATIENTS" });
    else if (cmd === "home") setRoute({ view: "HOME" });
    else alert("Unknown command");
  }

  return (
    <div className="container vstack">
      <div className="card vstack">
        <CommandBar onSubmit={handleCommand} />
        {route.view === "HOME" && <Home onCommand={handleCommand} />}
        {route.view === "QUEUE" && <QueueView stateFilter={route.state} />}
        {route.view === "PATIENT" && <PatientProfile pid={route.pid} />}
        {route.view === "DRUGS" && <DrugsView />}
        {route.view === "PATIENTS" && <PatientsView />}
      </div>
      <footer>API: {import.meta.env.VITE_API_BASE || "http://localhost:8000"}</footer>
    </div>
  );
}
