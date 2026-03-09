import { useState, useContext, useRef, useEffect } from "react";
import { AuthContext } from "@/context/AuthContext";
import { NotificationProvider, useNotification } from "@/context/NotificationContext";
import LoginForm from "@/components/LoginForm";
import NotificationPanel from "@/components/NotificationPanel";

import { searchPatients, generateTestPrescriptions, getPrescription } from "@/api";
import EditRefillView from "@/components/EditRefillView";
import RefillDetailView from "@/components/RefillDetailView";

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
import PatientSelectView from "@/components/PatientSelectView";
import RegisterView from "@/components/RegisterView";
import UserManagementView from "@/components/UserManagementView";
import AuditLogView from "@/components/AuditLogView";

const PATIENT_PAGE_SIZE = 15;

export default function AppRoot() {
  return (
    <NotificationProvider>
      <App />
    </NotificationProvider>
  );
}

function App() {
  const { isAuthenticated, shouldResetToHome, clearHomeReset, authUser, quickCode, clearQuickCode, token, logout } = useContext(AuthContext);
  const { addNotification } = useNotification();
  const [route, setRoute] = useState({ view: "HOME" });
  const [history, setHistory] = useState([]);
  const [currentPatientData, setCurrentPatientData] = useState(null);
  const [queueSelectRow, setQueueSelectRow] = useState(null);
  const [patientSelectRow, setPatientSelectRow] = useState(null);
  const [refillKeyCmd, setRefillKeyCmd] = useState(null);
  const [showHelp, setShowHelp] = useState(true);
  const cmdBarRef = useRef(null);
  // Track whether auth has ever been established in this session.
  // False = first-time login (show full-screen form), true = timeout (show modal overlay).
  const hasEverLoggedInRef = useRef(false);
  if (isAuthenticated) hasEverLoggedInRef.current = true;

  // When the 30-min idle-logout timer fires, reset to HOME and acknowledge.
  useEffect(() => {
    if (shouldResetToHome) {
      setHistory([]);
      setRoute({ view: "HOME" });
      clearHomeReset();
    }
  }, [shouldResetToHome, clearHomeReset]);

  useEffect(() => {
    cmdBarRef.current?.focus();
  }, [route]);

  // Drill-down navigation: pushes current route to history so `q` can go back
  function navigateTo(newRoute) {
    setHistory((prev) => [...prev, route]);
    setRoute(newRoute);
  }

  // Section navigation: clears history so `q` cannot return to a previous form/edit view
  function navigateToSection(newRoute) {
    setHistory([]);
    setRoute(newRoute);
  }

  function goBack() {
    if (history.length > 0) {
      const previous = history[history.length - 1];
      setHistory((prev) => prev.slice(0, -1));
      setRoute(previous);
    } else if (route.view !== "HOME") {
      setRoute({ view: "HOME" });
      setShowHelp(true);
    } else {
      setShowHelp(true);
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

    // Toggle help panel
    if (cmd === "?") {
      setShowHelp((prev) => !prev);
      return;
    }

    // Look up prescription by Rx ID: rx<id> (from any view)
    const rxMatch = cmd.match(/^rx(\d+)$/);
    if (rxMatch) {
      const rxId = parseInt(rxMatch[1], 10);
      getPrescription(rxId, token)
        .then((prescription) => {
          const p = prescription.patient;
          navigateTo({
            view: "VIEW_PRESCRIPTION",
            prescription,
            patientName: `${p.last_name}, ${p.first_name}`,
            patientId: p.id,
          });
        })
        .catch(() => addNotification(`Rx #${rxId} not found`, "error"));
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
          addNotification(`Row ${lineNum} not found`, "error");
        }
      }
      return;
    }

    // Check if input is a number (row selection)
    const rowNum = parseInt(cmd, 10);
    if (!isNaN(rowNum) && rowNum > 0) {
      // Handle row selection based on current view
      if (route.view === "QUEUE") {
        setQueueSelectRow(rowNum);
        return;
      }
      if (route.view === "PATIENT_SELECT") {
        setPatientSelectRow(rowNum);
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

    // Edit the currently viewed refill (only valid from the refill detail view)
    if (cmd === "e") {
      if (route.view === "REFILL_DETAIL") {
        navigateTo({ view: "EDIT_REFILL", refillId: route.refillId });
      }
      return;
    }

    // Approve / Hold shortcuts — only valid from refill detail view
    if (cmd === "a") {
      if (route.view === "REFILL_DETAIL") setRefillKeyCmd("approve");
      return;
    }
    if (cmd === "h") {
      if (route.view === "REFILL_DETAIL") setRefillKeyCmd("hold");
      return;
    }

    // Queue state commands — section navigation (clears history)
    if (["qt", "qv1", "qp", "qv2", "ready", "hold", "rejected"].includes(cmd)) {
      navigateToSection({ view: "QUEUE", state: cmd.toUpperCase() });
      return;
    }
    if (cmd === "all") {
      navigateToSection({ view: "QUEUE", state: "ALL" });
      return;
    }

    // Patient search (firstname,lastname or lastname,firstname)
    if (cmd.includes(",")) {
      const [partA = "", partB = ""] = input.split(",").map((s) => s.trim());
      if (partA.length < 3 || partB.length < 3) {
        addNotification("Please enter at least 3 characters for both first and last name.", "warning");
        return;
      }
      searchPatients(input, token)
        .then((list) => {
          if (list.length === 0) {
            navigateTo({ view: "NO_MATCH", query: input.trim() });
          } else if (list.length === 1) {
            navigateTo({ view: "PATIENT", pid: list[0].id });
          } else {
            navigateTo({ view: "PATIENT_SELECT", patients: list, query: input.trim() });
          }
        })
        .catch((e) => addNotification(e.message, "error"));
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

    // Top-level section commands — clears history so `q` cannot return to a previous form/edit view
    if (cmd === "drugs") navigateToSection({ view: "DRUGS" });
    else if (cmd === "pt" || cmd === "patients") navigateToSection({ view: "PATIENTS" });
    else if (cmd === "home") { navigateToSection({ view: "HOME" }); setShowHelp(true); }
    else if (cmd === "stock") navigateToSection({ view: "STOCK" });
    else if (cmd === "refill_hist") navigateToSection({ view: "REFILL_HIST" });
    else if (cmd === "prescribers") navigateToSection({ view: "PRESCRIBERS" });
    else if (cmd === "logout") logout();
    else if (cmd === "register") navigateToSection({ view: "REGISTER" });
    else if (cmd === "users") {
      if (!authUser?.isAdmin) { addNotification("Access denied: admin only.", "error"); return; }
      navigateToSection({ view: "USER_MANAGEMENT" });
    }
    else if (cmd === "logs") {
      if (!authUser?.isAdmin) { addNotification("Access denied: admin only.", "error"); return; }
      navigateToSection({ view: "AUDIT_LOG" });
    }
    else if (cmd === "gen_test") {
      if (confirm("This will DELETE all current prescriptions and refills and generate 50 new test prescriptions. Continue?")) {
        generateTestPrescriptions(token)
          .then((result) => {
            addNotification(`Created ${result.prescriptions_created} prescriptions\nActive refills: ${result.active_refills_created}\nSold refills: ${result.sold_prescriptions}`, "success");
            navigateTo({ view: "HOME" });
          })
          .catch((e) => addNotification(`Error: ${e.message}`, "error"));
      }
    }
    else addNotification("Unknown command", "warning");
  }

  // First-time visit (never logged in) — show full-screen login, nothing behind it.
  if (!isAuthenticated && !hasEverLoggedInRef.current) {
    return <LoginForm />;
  }

  const showLoginModal = !isAuthenticated;

  return (
    <div className="container vstack">
      <NotificationPanel />
      {/* Non-dismissible login modal — shown after session timeout */}
      {showLoginModal && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 9999,
            backgroundColor: "rgba(0, 0, 0, 0.6)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
          // Swallow all pointer and keyboard events so the background is unreachable
          onMouseDown={(e) => e.stopPropagation()}
          onClick={(e) => e.stopPropagation()}
          onKeyDown={(e) => { e.stopPropagation(); if (e.key === "Escape") e.preventDefault(); }}
        >
          <LoginForm isModal />
        </div>
      )}
      {/* Quick code banner — shown after login while a code is active */}
      {isAuthenticated && quickCode && (
        <QuickCodeBanner quickCode={quickCode} onDismiss={clearQuickCode} />
      )}

      <div className="card" style={{ padding: 0, display: "flex", flexDirection: "column", height: "calc(100vh - 120px)" }}>
        <div style={{ flex: 1, overflowY: "auto", padding: "24px", minHeight: 0 }}>
          {route.view === "HOME" && showHelp && <Home onCommand={handleCommand} />}
          {route.view === "HOME" && !showHelp && (
            <div style={{ color: "var(--text-light)", textAlign: "center", paddingTop: "2rem" }}>
              Type <strong>?</strong> to show help
            </div>
          )}
          {route.view === "QUEUE" && (
            <QueueView
              stateFilter={route.state}
              onBack={goBack}
              onSelectRow={queueSelectRow}
              page={route.page || 1}
              onSelectRefill={(refillId) => {
                setQueueSelectRow(null);
                navigateTo({ view: "REFILL_DETAIL", refillId, fromQueueState: route.state });
              }}
            />
          )}
          {route.view === "REFILL_DETAIL" && (
            <RefillDetailView
              refillId={route.refillId}
              onBack={goBack}
              onEdit={() => navigateTo({ view: "EDIT_REFILL", refillId: route.refillId })}
              onUpdate={(updated) => navigateToSection({ view: "QUEUE", state: updated.state })}
              keyCmd={refillKeyCmd}
              onKeyCmdHandled={() => setRefillKeyCmd(null)}
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
          {route.view === "EDIT_REFILL" && (
            <EditRefillView
              refillId={route.refillId}
              onBack={goBack}
              onSaved={(updated) => {
                navigateToSection({ view: "QUEUE", state: updated.state });
              }}
            />
          )}
          {route.view === "DRUGS" && (
            <DrugsView
              onBack={goBack}
              page={route.page || 1}
              onSelectDrug={(drugId) => {
                // Future: navigate to drug detail view
                addNotification(`Drug ID: ${drugId}`, "info");
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
                addNotification(`Drug ID: ${drugId}`, "info");
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
                addNotification(`Prescriber ID: ${prescriberId}`, "info");
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
          {route.view === "PATIENT_SELECT" && (
            <PatientSelectView
              patients={route.patients}
              query={route.query}
              onSelectRow={patientSelectRow}
              onSelect={(pid) => {
                setPatientSelectRow(null);
                navigateTo({ view: "PATIENT", pid });
              }}
            />
          )}
          {route.view === "REGISTER" && <RegisterView onBack={goBack} />}
          {route.view === "USER_MANAGEMENT" && <UserManagementView onBack={goBack} />}
          {route.view === "AUDIT_LOG" && <AuditLogView onBack={goBack} page={route.page || 1} />}
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
        {!showLoginModal && <CommandBar ref={cmdBarRef} onSubmit={handleCommand} />}
      </div>
      <footer>
        <strong>JoeMed</strong> Pharmacy Management System | API: {import.meta.env.VITE_API_BASE || "http://localhost:8000"}
      </footer>
    </div>
  );
}

function QuickCodeBanner({ quickCode, onDismiss }) {
  const [remaining, setRemaining] = useState(null);

  useEffect(() => {
    function tick() {
      const secs = Math.max(0, Math.round((quickCode.expiresAt - Date.now()) / 1000));
      setRemaining(secs);
      if (secs === 0) onDismiss();
    }
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [quickCode, onDismiss]);

  if (remaining === null || remaining === 0) return null;

  return (
    <div
      style={{
        background: "rgba(6, 214, 160, 0.1)",
        border: "1px solid var(--success, #06d6a0)",
        borderRadius: 8,
        padding: "10px 16px",
        display: "flex",
        alignItems: "center",
        gap: 16,
        marginBottom: 8,
      }}
    >
      <div style={{ flex: 1, textAlign: "center" }}>
        <span style={{ fontSize: "0.8rem", color: "white" }}>Your quick login code: </span>
        <span style={{ fontSize: "1.3rem", fontWeight: 800, letterSpacing: "0.3em", fontFamily: "monospace", color: "var(--primary)" }}>
          {quickCode.code}
        </span>
        <span style={{ fontSize: "0.75rem", color: "white", marginLeft: 10 }}>
          (expires in {Math.floor(remaining / 60)}:{String(remaining % 60).padStart(2, "0")})
        </span>
      </div>
      <button
        onClick={onDismiss}
        style={{ background: "none", border: "none", cursor: "pointer", fontSize: "1rem", color: "var(--text-light)", lineHeight: 1 }}
        title="Dismiss"
      >
        ✕
      </button>
    </div>
  );
}
