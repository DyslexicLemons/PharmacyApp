import { useState, useContext, useRef, useEffect } from "react";
import { DataContext } from "@/context/DataContext";

import { searchPatients, generateTestPrescriptions, getPrescription } from "@/api";

import PatientProfile from "@/components/PatientProfile";
import DrugsView from "@/components/DrugsView";
import PatientsView from "@/components/PatientsView";
import QueueView from "@/components/QueueView";
import Home from "@/components/Home";
import CommandBar from "@/components/CommandBar";
import StockView from "@/components/StockView";
import RefillHistView from "@/components/RefillHistView";
import PrescribersView from "@/components/PrescribersView";
import PrescriptionForm from "@/components/PrescriptionForm";
import FillScriptView from "@/components/FillScriptView";
import PrescriptionDetailView from "@/components/PrescriptionDetailView";
import NewPatientForm from "@/components/NewPatientForm";
import RegisterView from "@/components/RegisterView";

const PATIENT_PAGE_SIZE = 15;

export default function App() {
  const [route, setRoute] = useState({ view: "HOME" });
  const [history, setHistory] = useState([]);
  const [currentPatientData, setCurrentPatientData] = useState(null);
  const { patients, drugs, stock, prescribers } = useContext(DataContext);
  const cmdBarRef = useRef(null);

  useEffect(() => {
    cmdBarRef.current?.focus();
  }, [route]);

  function navigateTo(newRoute) {
    setHistory((prev) => [...prev, route]);
    setRoute(newRoute);
  }

  function goBack() {
    if (history.length > 0) {
      const previous = history[history.length - 1];
      setHistory((prev) => prev.slice(0, -1));
      setRoute(previous);
    }
  }

  function handleCommand(input) {
    const tempCmd = input.toLowerCase();
    if (tempCmd === " ") {
            if (route.view !== "HOME" && route.view !== "PATIENT") return;
      navigateTo({
        view: "CREATE_PRESCRIPTION",
        patientId: route.view === "PATIENT" ? route.pid : undefined,
      });
      return;
    }
    const cmd = input.toLowerCase().trim();

    // Look up prescription by Rx ID: rx<id> (from any view)
    const rxMatch = cmd.match(/^rx(\d+)$/);
    if (rxMatch) {
      const rxId = parseInt(rxMatch[1], 10);
      getPrescription(rxId)
        .then((prescription) => {
          const p = prescription.patient;
          navigateTo({
            view: "VIEW_PRESCRIPTION",
            prescription,
            patientName: `${p.last_name}, ${p.first_name}`,
            patientId: p.id,
          });
        })
        .catch(() => alert(`Rx #${rxId} not found`));
      return;
    }

    // View prescription detail: Vx (only in PATIENT view)
    const viewMatch = cmd.match(/^v(\d+)$/);
    if (viewMatch && route.view === "PATIENT") {
      const lineNum = parseInt(viewMatch[1], 10);
      if (currentPatientData) {
        const page = route.page || 1;
        const idx = (page - 1) * PATIENT_PAGE_SIZE + (lineNum - 1);
        const prescription = currentPatientData.prescriptions[idx];
        if (prescription) {
          navigateTo({
            view: "VIEW_PRESCRIPTION",
            prescription,
            patientName: `${currentPatientData.last_name}, ${currentPatientData.first_name}`,
            patientId: currentPatientData.id,
          });
        } else {
          alert(`Row ${lineNum} not found`);
        }
      }
      return;
    }

    // Check if input is a number (row selection)
    const rowNum = parseInt(cmd, 10);
    if (!isNaN(rowNum) && rowNum > 0) {
      // Handle row selection based on current view
      if (route.view === "PATIENTS") {
        const index = rowNum - 1;
        if (index >= 0 && index < patients.length) {
          navigateTo({ view: "PATIENT", pid: patients[index].id });
        } else {
          alert(`Row ${rowNum} not found in patients list`);
        }
        return;
      } else if (route.view === "DRUGS") {
        const index = rowNum - 1;
        if (index >= 0 && index < drugs.length) {
          // For now, just show alert. Add drug detail view later if needed
          alert(`Drug ${rowNum}: ${drugs[index].drug_name}`);
        } else {
          alert(`Row ${rowNum} not found in drugs list`);
        }
        return;
      } else if (route.view === "STOCK") {
        const index = rowNum - 1;
        if (index >= 0 && index < stock.length) {
          // For now, just show alert. Add stock detail view later if needed
          alert(`Stock ${rowNum}: ${stock[index].drug.drug_name}`);
        } else {
          alert(`Row ${rowNum} not found in stock list`);
        }
        return;
      } else if (route.view === "PRESCRIBERS") {
        const index = rowNum - 1;
        if (index >= 0 && index < prescribers.length) {
          // For now, just show alert. Add prescriber detail view later if needed
          alert(`Prescriber ${rowNum}: ${prescribers[index].first_name} ${prescribers[index].last_name}`);
        } else {
          alert(`Row ${rowNum} not found in prescribers list`);
        }
        return;
      } else if (route.view === "QUEUE") {
        // For Queue, update the route with the selected row number
        navigateTo({ view: "QUEUE", state: route.state, selectRow: rowNum });
        return;
      }
    }

    if (cmd === "q") {
      goBack();
      return;
    }

    if (cmd === "n") {
      setRoute((prev) => ({ ...prev, page: (prev.page || 1) + 1 }));
      return;
    }
    if (cmd === "p") {
      setRoute((prev) => {
        const current = prev.page || 1;
        return current > 1 ? { ...prev, page: current - 1 } : prev;
      });
      return;
    }

    // New state-specific queue commands
    if (["qt", "qv1", "qp", "qv2", "ready", "hold", "rejected"].includes(cmd)) {
      navigateTo({ view: "QUEUE", state: cmd.toUpperCase() });
      return;
    }
    if (cmd === "all") {
      navigateTo({ view: "QUEUE", state: "ALL" });
      return;
    }

    // Patient search (lastname,firstname)
    if (cmd.includes(",")) {
      searchPatients(input)
        .then((list) => {
          if (list.length === 0) {
            navigateTo({ view: "NO_MATCH", query: input.trim() });
          } else if (list.length === 1) {
            navigateTo({ view: "PATIENT", pid: list[0].id });
          } else {
            const names = list
              .map((p) => `${p.id}: ${p.last_name}, ${p.first_name}`)
              .join("\n");
            const pick = prompt(`Multiple matches. Enter ID to open:\n${names}`);
            const chosen = list.find((p) => String(p.id) === String(pick));
            if (chosen) navigateTo({ view: "PATIENT", pid: chosen.id });
          }
        })
        .catch((e) => alert(e.message));
      return;
    }

    // Single space = create new prescription (only from HOME or PATIENT views)
    if (input.trim() === "" && input !== "") {
      if (route.view !== "HOME" && route.view !== "PATIENT") return;
      navigateTo({
        view: "CREATE_PRESCRIPTION",
        patientId: route.view === "PATIENT" ? route.pid : undefined,
      });
      return;
    }

    // Command shortcuts
    if (cmd === "drugs") navigateTo({ view: "DRUGS" });
    else if (cmd === "pt" || cmd === "patients") navigateTo({ view: "PATIENTS" });
    else if (cmd === "home") navigateTo({ view: "HOME" });
    else if (cmd === "stock") navigateTo({ view: "STOCK" });
    else if (cmd === "refill_hist") navigateTo({ view: "REFILL_HIST" });
    else if (cmd === "prescribers") navigateTo({ view: "PRESCRIBERS" });
    else if (cmd === "register") navigateTo({ view: "REGISTER" });
    else if (cmd === "gen_test") {
      if (confirm("This will DELETE all current prescriptions and refills and generate 50 new test prescriptions. Continue?")) {
        generateTestPrescriptions()
          .then((result) => {
            alert(`Success!\n\nCreated ${result.prescriptions_created} prescriptions\nActive refills: ${result.active_refills_created}\nSold refills: ${result.sold_prescriptions}`);
            navigateTo({ view: "HOME" });
          })
          .catch((e) => alert(`Error: ${e.message}`));
      }
    }
    else alert("Unknown command");
  }

  return (
    <div className="container vstack">
      <div className="card" style={{ padding: 0, display: "flex", flexDirection: "column", height: "calc(100vh - 120px)" }}>
        <div style={{ flex: 1, overflowY: "auto", padding: "24px", minHeight: 0 }}>
          {route.view === "HOME" && <Home onCommand={handleCommand} />}
          {route.view === "QUEUE" && (
            <QueueView
              stateFilter={route.state}
              onBack={goBack}
              onSelectRow={route.selectRow}
              page={route.page || 1}
            />
          )}
          {route.view === "PATIENT" && (
            <PatientProfile
              pid={route.pid}
              onBack={goBack}
              page={route.page || 1}
              onDataLoaded={(d) => setCurrentPatientData(d)}
              onFill={(prescription, patient) =>
                navigateTo({
                  view: "FILL_SCRIPT",
                  prescription,
                  patientName: `${patient.last_name}, ${patient.first_name}`,
                  fromPid: route.pid,
                })
              }
            />
          )}
          {route.view === "VIEW_PRESCRIPTION" && (
            <PrescriptionDetailView
              prescription={route.prescription}
              patientName={route.patientName}
              patientId={route.patientId}
              onBack={goBack}
            />
          )}
          {route.view === "FILL_SCRIPT" && (
            <FillScriptView
              prescription={route.prescription}
              patientName={route.patientName}
              patientId={route.fromPid}
              onBack={goBack}
            />
          )}
          {route.view === "DRUGS" && (
            <DrugsView
              onBack={goBack}
              page={route.page || 1}
              onSelectDrug={(drugId) => {
                // Future: navigate to drug detail view
                alert(`Drug ID: ${drugId}`);
              }}
            />
          )}
          {route.view === "PATIENTS" && (
            <PatientsView
              onBack={goBack}
              page={route.page || 1}
              onSelectPatient={(patientId) => {
                navigateTo({ view: "PATIENT", pid: patientId });
              }}
            />
          )}
          {route.view === "STOCK" && (
            <StockView
              onBack={goBack}
              page={route.page || 1}
              onSelectStock={(drugId) => {
                // Future: navigate to stock detail view
                alert(`Drug ID: ${drugId}`);
              }}
            />
          )}
          {route.view === "REFILL_HIST" && <RefillHistView onBack={goBack} page={route.page || 1} />}
          {route.view === "PRESCRIBERS" && (
            <PrescribersView
              onBack={goBack}
              page={route.page || 1}
              onSelectPrescriber={(prescriberId) => {
                // Future: navigate to prescriber detail view
                alert(`Prescriber ID: ${prescriberId}`);
              }}
            />
          )}
          {route.view === "CREATE_PRESCRIPTION" && (
            <PrescriptionForm onBack={goBack} patientId={route.patientId} />
          )}
          {route.view === "NO_MATCH" && (
            <div className="vstack" style={{ alignItems: "center", justifyContent: "center", height: "100%", gap: "1.5rem" }}>
              <div style={{ fontSize: "1.1rem", color: "var(--text-light)" }}>
                No matches for <strong>"{route.query}"</strong>
              </div>
              <div style={{ fontSize: "1.05rem" }}>Create a new patient?</div>
              <div style={{ display: "flex", gap: "1rem" }}>
                <button
                  className="btn btn-primary"
                  onClick={() => {
                    const [last = "", first = ""] = route.query.split(",").map((s) => s.trim());
                    navigateTo({ view: "CREATE_PATIENT", prefillLast: last, prefillFirst: first });
                  }}
                >
                  Yes
                </button>
                <button className="btn btn-secondary" onClick={goBack}>
                  No
                </button>
              </div>
            </div>
          )}
          {route.view === "REGISTER" && <RegisterView onBack={goBack} />}
          {route.view === "CREATE_PATIENT" && (
            <NewPatientForm
              prefillLast={route.prefillLast}
              prefillFirst={route.prefillFirst}
              onBack={goBack}
              onCreated={(patient) => {
                navigateTo({ view: "PATIENT", pid: patient.id });
              }}
            />
          )}
        </div>
        <CommandBar ref={cmdBarRef} onSubmit={handleCommand} />
      </div>
      <footer>
        <strong>JoeMed</strong> Pharmacy Management System | API: {import.meta.env.VITE_API_BASE || "http://localhost:8000"}
      </footer>
    </div>
  );
}
