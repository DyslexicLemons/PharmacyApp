import { useState, useContext, useRef, useEffect, lazy, Suspense } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { AuthContext } from "@/context/AuthContext";
import { NotificationProvider, useNotification } from "@/context/NotificationContext";
import LoginForm from "@/components/LoginForm";
import NotificationPanel from "@/components/NotificationPanel";
import Logo from "@/components/Logo";
import CommandBar from "@/components/CommandBar";

import { searchPatients, generateTestPrescriptions, getPrescription, deletePatient } from "@/api";
import QueueSidebar from "@/components/QueueSidebar";
import type { RouteState } from "@/types";

// Route-level components are lazy-loaded so each view becomes its own chunk.
// LoginForm and CommandBar stay eager — they are needed before/after any route.
const EditRefillView        = lazy(() => import("@/components/EditRefillView"));
const RefillDetailView      = lazy(() => import("@/components/RefillDetailView"));
const PatientProfile        = lazy(() => import("@/components/PatientProfile"));
const DrugsView             = lazy(() => import("@/components/DrugsView"));
const PatientsView          = lazy(() => import("@/components/PatientsView"));
const QueueView             = lazy(() => import("@/components/QueueView"));
const Home                  = lazy(() => import("@/components/Home"));
const StockView             = lazy(() => import("@/components/StockView"));
const RefillHistView        = lazy(() => import("@/components/RefillHistView"));
const PrescribersView       = lazy(() => import("@/components/PrescribersView"));
const PrescriptionForm      = lazy(() => import("@/components/PrescriptionForm"));
const FillScriptView        = lazy(() => import("@/components/FillScriptView"));
const PrescriptionDetailView = lazy(() => import("@/components/PrescriptionDetailView"));
const NewPatientForm        = lazy(() => import("@/components/NewPatientForm"));
const PatientSelectView     = lazy(() => import("@/components/PatientSelectView"));
const RegisterView          = lazy(() => import("@/components/RegisterView"));
const UserManagementView    = lazy(() => import("@/components/UserManagementView"));
const AuditLogView          = lazy(() => import("@/components/AuditLogView"));
const ShipmentView          = lazy(() => import("@/components/ShipmentView"));
const ShipmentHistView      = lazy(() => import("@/components/ShipmentHistView"));
const SystemSettingsView    = lazy(() => import("@/components/SystemSettingsView"));
const AdminConsoleView      = lazy(() => import("@/components/AdminConsoleView"));
const RTSView               = lazy(() => import("@/components/RTSView"));
const RTSHistView           = lazy(() => import("@/components/RTSHistView"));
const WorkerDashboardView   = lazy(() => import("@/components/WorkerDashboardView"));
const ProviderInfoView      = lazy(() => import("@/components/ProviderInfoView"));
const EditPatientView       = lazy(() => import("@/components/EditPatientView"));
const DashboardView         = lazy(() => import("@/components/DashboardView"));

function ViewFallback() {
  return (
    <div style={{ padding: "2rem", textAlign: "center", color: "var(--text-light)" }}>
      Loading…
    </div>
  );
}

const PATIENT_PAGE_SIZE = 15;

interface HintEntry { key: string; label: string; danger?: boolean }

function getViewHints(
  view: string,
  deletePendingPid: number | null,
  totalPages: number,
  page: number,
): HintEntry[] {
  const hasPagination = totalPages > 1 || page > 1;
  const pageHint: HintEntry = { key: "[n]/[p]", label: "Next/prev page" };
  const backHint: HintEntry = { key: "[q]", label: "Back" };
  const hideHint: HintEntry = { key: "[?]", label: "Hide hints" };

  switch (view) {
    case "PATIENT":
      return [
        { key: "[e]", label: "Edit patient" },
        { key: "[d]", label: "Delete patient", danger: deletePendingPid !== null },
        { key: "[#]", label: "View prescription" },
        { key: "[space]", label: "New prescription" },
        ...(hasPagination ? [pageHint] : []),
        backHint, hideHint,
      ];
    case "QUEUE":
      return [
        { key: "[#]", label: "Open refill" },
        { key: "[qt/qv1/qp/qv2]", label: "Filter by state" },
        { key: "[ready/hold/rejected]", label: "More state filters" },
        ...(hasPagination ? [pageHint] : []),
        backHint, hideHint,
      ];
    case "VIEW_PRESCRIPTION":
      return [
        { key: "[h]", label: "Hold" },
        { key: "[i]", label: "Inactivate" },
        backHint, hideHint,
      ];
    case "REFILL_DETAIL":
      return [
        { key: "[e]", label: "Edit" },
        { key: "[a]", label: "Approve" },
        { key: "[h]", label: "Hold" },
        backHint, hideHint,
      ];
    case "PATIENTS":
    case "PATIENT_SELECT":
      return [
        { key: "[#]", label: "Select patient" },
        ...(hasPagination ? [pageHint] : []),
        backHint, hideHint,
      ];
    case "SHIPMENT":
      return [
        { key: "[f]", label: "Finish shipment" },
        backHint, hideHint,
      ];
    case "STOCK":
      return [
        { key: "[rts]", label: "Return to stock" },
        ...(hasPagination ? [pageHint] : []),
        backHint, hideHint,
      ];
    case "DRUGS":
    case "REFILL_HIST":
    case "PRESCRIBERS":
    case "AUDIT_LOG":
    case "RTS_HIST":
    case "SHIPMENT_HIST":
      return [...(hasPagination ? [pageHint] : []), backHint, hideHint];
    case "EDIT_REFILL":
    case "EDIT_PATIENT":
    case "CREATE_PRESCRIPTION":
    case "CREATE_PATIENT":
    case "FILL_SCRIPT":
    case "REGISTER":
    case "USER_MANAGEMENT":
    case "SYSTEM_SETTINGS":
    case "ADMIN_CONSOLE":
    case "WORKER_DASHBOARD":
    case "PROVIDER_INFO":
      return [{ key: "[q]", label: "Cancel / back" }, hideHint];
    default:
      return [backHint, hideHint];
  }
}

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
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<"workflow" | "dashboard">("workflow");
  const [route, setRoute] = useState<RouteState>({ view: "HOME" });
  const [history, setHistory] = useState<RouteState[]>([]);
  const [currentPatientData, setCurrentPatientData] = useState<{ id: number; first_name: string; last_name: string; prescriptions: unknown[] } | null>(null);
  const [queueSelectRow, setQueueSelectRow] = useState<number | null>(null);
  const [patientSelectRow, setPatientSelectRow] = useState<number | null>(null);
  const [refillKeyCmd, setRefillKeyCmd] = useState<string | null>(null);
  const [prescriptionKeyCmd, setPrescriptionKeyCmd] = useState<string | null>(null);
  const [shipmentKeyCmd, setShipmentKeyCmd] = useState<string | null>(null);
  const [showHelp, setShowHelp] = useState(true);
  const [deletePendingPid, setDeletePendingPid] = useState<number | null>(null);
  const [currentTotalPages, setCurrentTotalPages] = useState(Infinity);
  const cmdBarRef = useRef<{ focus: () => void } | null>(null);
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
    setCurrentTotalPages(Infinity);
    if (route.view !== "PATIENT") {
      setDeletePendingPid(null);
    }
  }, [route.view]);

  useEffect(() => {
    cmdBarRef.current?.focus();
  }, [route]);

  useEffect(() => {
    if (route.view === "QUEUE") {
      queryClient.invalidateQueries({ queryKey: ["queue-summary"] });
    }
  }, [route]);

  // Drill-down navigation: pushes current route to history so `q` can go back
  function navigateTo(newRoute: RouteState) {
    setHistory((prev) => [...prev, route]);
    setRoute(newRoute);
  }

  // Section navigation: clears history so `q` cannot return to a previous form/edit view
  function navigateToSection(newRoute: RouteState) {
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
    }
  }

  // After a successful fill, skip VIEW_PRESCRIPTION and return to wherever the
  // user was before entering the prescription detail (e.g. patient profile or
  // whatever view was active when they ran an rx<id> command).
  function onFillSuccess() {
    const prevRoute = history.length > 0 ? history[history.length - 1] : null;
    if (prevRoute?.view === "VIEW_PRESCRIPTION") {
      if (history.length >= 2) {
        const target = history[history.length - 2];
        setHistory((prev) => prev.slice(0, -2));
        setRoute(target);
      } else {
        setHistory([]);
        setRoute({ view: "HOME" });
      }
    } else {
      goBack();
    }
  }

  function handleCommand(input: string) {
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

    // Return-to-stock: rts<id> goes directly to confirm, rts alone opens lookup
    const rtsMatch = cmd.match(/^rts(\d+)$/);
    if (rtsMatch) {
      navigateToSection({ view: "RTS_LOOKUP", refillId: parseInt(rtsMatch[1], 10) });
      return;
    }
    if (cmd === "rts") {
      navigateToSection({ view: "RTS_LOOKUP" });
      return;
    }
    if (cmd === "rts_hist") {
      navigateToSection({ view: "RTS_HIST" });
      return;
    }

    // Look up prescription by Rx ID: rx<id> (from any view)
    const rxMatch = cmd.match(/^rx(\d+)$/);
    if (rxMatch) {
      const rxId = parseInt(rxMatch[1], 10);
      getPrescription(rxId, token!)
        .then((prescription) => {
          const p = prescription.patient;
          navigateTo({
            view: "VIEW_PRESCRIPTION",
            prescription,
            patientName: p ? `${p.last_name}, ${p.first_name}` : "Unknown",
            patientId: p?.id ?? 0,
          });
        })
        .catch(() => addNotification(`Rx #${rxId} not found`, "error"));
      return;
    }

    // Check if input is a number (row selection)
    const rowNum = parseInt(cmd, 10);
    if (!isNaN(rowNum) && rowNum > 0) {
      if (route.view === "QUEUE") {
        setQueueSelectRow(rowNum);
        return;
      }
      if (route.view === "PATIENT_SELECT") {
        setPatientSelectRow(rowNum);
        return;
      }
      if (route.view === "PATIENT") {
        if (currentPatientData) {
          const page = route.page || 1;
          const idx = (page - 1) * PATIENT_PAGE_SIZE + (rowNum - 1);
          const prescription = (currentPatientData.prescriptions as unknown[])[idx];
          if (prescription) {
            navigateTo({
              view: "VIEW_PRESCRIPTION",
              prescription: prescription as import("@/types").Prescription,
              patientName: `${currentPatientData.last_name}, ${currentPatientData.first_name}`,
              patientId: currentPatientData.id,
            });
          } else {
            addNotification(`Row ${rowNum} not found`, "error");
          }
        }
        return;
      }
    }

    if (cmd === "q") {
      if (deletePendingPid !== null) {
        setDeletePendingPid(null);
      } else {
        goBack();
      }
      return;
    }

    // Delete patient — two-step: 'd' arms the confirmation, 'confirm' executes
    if (cmd === "d") {
      if (route.view === "PATIENT") {
        setDeletePendingPid(route.pid);
      }
      return;
    }
    if (cmd === "confirm") {
      if (deletePendingPid !== null) {
        const pidToDelete = deletePendingPid;
        setDeletePendingPid(null);
        deletePatient(pidToDelete, token!)
          .then(() => {
            addNotification("Patient deleted.", "success");
            goBack();
          })
          .catch((e: Error) => addNotification(e.message, "error"));
      }
      return;
    }

    if (cmd === "n") {
      setRoute((prev) => {
        const current = ("page" in prev ? prev.page : undefined) || 1;
        return current < currentTotalPages ? { ...prev, page: current + 1 } : prev;
      });
      return;
    }
    if (cmd === "p") {
      setRoute((prev) => {
        const current = ("page" in prev ? prev.page : undefined) || 1;
        return current > 1 ? { ...prev, page: current - 1 } : prev;
      });
      return;
    }

    // Edit the currently viewed refill (refill detail) or patient (patient profile)
    if (cmd === "e") {
      if (route.view === "REFILL_DETAIL") {
        navigateTo({ view: "EDIT_REFILL", refillId: route.refillId });
      } else if (route.view === "PATIENT") {
        navigateTo({ view: "EDIT_PATIENT", pid: route.pid });
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
      else if (route.view === "VIEW_PRESCRIPTION") setPrescriptionKeyCmd("hold");
      return;
    }
    if (cmd === "i") {
      if (route.view === "VIEW_PRESCRIPTION") setPrescriptionKeyCmd("inactivate");
      return;
    }
    if (cmd === "f") {
      if (route.view === "VIEW_PRESCRIPTION") setPrescriptionKeyCmd("fill");
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
      searchPatients(input, token!)
        .then((list) => {
          if (list.length === 0) {
            navigateTo({ view: "NO_MATCH", query: input.trim() });
          } else if (list.length === 1) {
            navigateTo({ view: "PATIENT", pid: list[0].id });
          } else {
            navigateTo({ view: "PATIENT_SELECT", patients: list, query: input.trim() });
          }
        })
        .catch((e: Error) => addNotification(e.message, "error"));
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

    // Finish shipment — only valid from SHIPMENT view
    if (cmd === "finished" || cmd === "f") {
      if (route.view === "SHIPMENT") setShipmentKeyCmd("finish");
      return;
    }

    // Top-level section commands — clears history so `q` cannot return to a previous form/edit view
    if (cmd === "drugs") navigateToSection({ view: "DRUGS" });
    else if (cmd === "pt" || cmd === "patients") navigateToSection({ view: "PATIENTS" });
    else if (cmd === "home") { navigateToSection({ view: "HOME" }); setShowHelp(true); }
    else if (cmd === "stock") navigateToSection({ view: "STOCK" });
    else if (cmd === "refill_hist") navigateToSection({ view: "REFILL_HIST" });
    else if (cmd === "prescribers") navigateToSection({ view: "PRESCRIBERS" });
    else if (cmd === "shipment") navigateToSection({ view: "SHIPMENT" });
    else if (cmd === "shipment_hist") navigateToSection({ view: "SHIPMENT_HIST" });
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
    else if (cmd === "settings") {
      if (!authUser?.isAdmin) { addNotification("Access denied: admin only.", "error"); return; }
      navigateToSection({ view: "SYSTEM_SETTINGS" });
    }
    else if (cmd === "admin") {
      if (!authUser?.isAdmin) { addNotification("Access denied: admin only.", "error"); return; }
      navigateToSection({ view: "ADMIN_CONSOLE" });
    }
    else if (cmd === "workers") navigateToSection({ view: "WORKER_DASHBOARD" });
    else if (cmd === "info") navigateToSection({ view: "PROVIDER_INFO" });
    else if (cmd === "gen_test") {
      if (confirm("This will DELETE all current prescriptions and refills and generate 50 new test prescriptions. Continue?")) {
        generateTestPrescriptions(token!)
          .then((result) => {
            addNotification(`Created ${result.prescriptions_created} prescriptions\nActive refills: ${result.active_refills_created}\nSold refills: ${result.sold_prescriptions}`, "success");
            navigateTo({ view: "HOME" });
          })
          .catch((e: Error) => addNotification(`Error: ${e.message}`, "error"));
      }
    }
    else if (cmd === "seed_insurance") {
      if (!authUser?.isAdmin) { addNotification("Access denied: admin only.", "error"); return; }
      fetch("/api/v1/commands/seed_insurance_companies", { method: "POST", headers: { Authorization: `Bearer ${token}` } })
        .then((r) => r.json())
        .then((result: { companies_added: number; formulary_entries_added: number }) => {
          if (result.companies_added === 0) {
            addNotification("Insurance companies already seeded — nothing added.", "info");
          } else {
            addNotification(`Seeded ${result.companies_added} insurance companies and ${result.formulary_entries_added} formulary entries.`, "success");
          }
        })
        .catch((e: Error) => addNotification(`Error: ${e.message}`, "error"));
    }
    else {
      const display = cmd.length > 30 ? cmd.slice(0, 30) + "…" : cmd;
      addNotification(`Unknown command: "${display}"`, "warning");
    }
  }

  // First-time visit (never logged in) — show full-screen login, nothing behind it.
  if (!isAuthenticated && !hasEverLoggedInRef.current) {
    return <LoginForm />;
  }

  const showLoginModal = !isAuthenticated;

  return (
    <div className="container vstack" style={{ height: "100vh", gap: 0 }}>
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
      {/* Top header with tab navigation */}
      <div style={{ display: "flex", alignItems: "center", padding: "8px 16px", flexShrink: 0, gap: "24px" }}>
        <Logo size={40} horizontal showTagline={false} />
        {isAuthenticated && (
          <nav style={{ display: "flex", gap: "2px", background: "rgba(255,255,255,0.1)", borderRadius: "8px", padding: "3px" }}>
            {(["workflow", "dashboard"] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                style={{
                  padding: "5px 18px",
                  borderRadius: "6px",
                  border: "none",
                  cursor: "pointer",
                  fontSize: "0.85rem",
                  fontWeight: 600,
                  transition: "all 0.15s ease",
                  background: activeTab === tab ? "rgba(255,255,255,0.95)" : "transparent",
                  color: activeTab === tab ? "var(--primary)" : "rgba(255,255,255,0.8)",
                  boxShadow: activeTab === tab ? "0 1px 4px rgba(0,0,0,0.15)" : "none",
                }}
              >
                {tab === "workflow" ? "RX Workflow" : "Dashboard"}
              </button>
            ))}
          </nav>
        )}
      </div>
      <div style={{ display: "flex", gap: "16px", flex: 1, minHeight: 0, alignItems: "stretch" }}>
      <div className="card" style={{ padding: 0, display: "flex", flexDirection: "column", flex: 1, minWidth: 0, overflow: "hidden" }}>
        <div style={{ flex: 1, overflowY: "auto", padding: "24px", minHeight: 0 }}>
          <Suspense fallback={<ViewFallback />}>
          {activeTab === "dashboard" && <DashboardView />}
          {activeTab === "workflow" && route.view === "HOME" && showHelp && <Home isAdmin={authUser?.isAdmin} />}
          {activeTab === "workflow" && route.view === "HOME" && !showHelp && (
            <div style={{ color: "var(--text-light)", textAlign: "center", paddingTop: "2rem" }}>
              Type <strong>?</strong> to show help
            </div>
          )}
          {activeTab === "workflow" && (<>
          {route.view === "QUEUE" && (
            <QueueView
              stateFilter={route.state}
              onBack={goBack}
              onSelectRow={queueSelectRow}
              page={route.page || 1}
              onTotalPages={setCurrentTotalPages}
              onSelectRefill={(refillId) => {
                setQueueSelectRow(null);
                navigateTo({ view: "REFILL_DETAIL", refillId, fromQueueState: route.state });
              }}
            />
          )}
          {route.view === "REFILL_DETAIL" && (
            <RefillDetailView
              refillId={route.refillId}
              fromQueueState={route.fromQueueState}
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
              onTotalPages={setCurrentTotalPages}
              onDataLoaded={(d) => setCurrentPatientData(d)}
              deletePending={deletePendingPid === route.pid}
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
          {route.view === "EDIT_PATIENT" && (
            <EditPatientView
              pid={route.pid}
              onBack={goBack}
              onSaved={() => {
                setCurrentPatientData(null);
                navigateTo({ view: "PATIENT", pid: route.pid });
              }}
            />
          )}
          {route.view === "VIEW_PRESCRIPTION" && (
            <PrescriptionDetailView
              prescription={route.prescription}
              patientName={route.patientName}
              patientId={route.patientId}
              onBack={goBack}
              onFill={() => navigateTo({
                view: "FILL_SCRIPT",
                prescription: route.prescription,
                patientName: route.patientName,
                fromPid: route.patientId,
              })}
              keyCmd={prescriptionKeyCmd}
              onKeyCmdHandled={() => setPrescriptionKeyCmd(null)}
            />
          )}
          {route.view === "FILL_SCRIPT" && (
            <FillScriptView
              prescription={route.prescription}
              patientName={route.patientName}
              patientId={route.fromPid}
              onBack={goBack}
              onSuccess={onFillSuccess}
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
              onTotalPages={setCurrentTotalPages}
              onSelectDrug={(drugId) => {
                addNotification(`Drug ID: ${drugId}`, "info");
              }}
            />
          )}
          {route.view === "PATIENTS" && (
            <PatientsView
              onBack={goBack}
              page={route.page || 1}
              onTotalPages={setCurrentTotalPages}
              onSelectPatient={(patientId) => {
                navigateTo({ view: "PATIENT", pid: patientId });
              }}
            />
          )}
          {route.view === "STOCK" && (
            <StockView
              onBack={goBack}
              page={route.page || 1}
              onTotalPages={setCurrentTotalPages}
              onSelectStock={(drugId) => {
                addNotification(`Drug ID: ${drugId}`, "info");
              }}
            />
          )}
          {route.view === "REFILL_HIST" && <RefillHistView onBack={goBack} page={route.page || 1} onTotalPages={setCurrentTotalPages} />}
          {route.view === "PRESCRIBERS" && (
            <PrescribersView
              onBack={goBack}
              page={route.page || 1}
              onTotalPages={setCurrentTotalPages}
              onSelectPrescriber={(prescriberId) => {
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
          {route.view === "SYSTEM_SETTINGS" && <SystemSettingsView onBack={goBack} />}
          {route.view === "ADMIN_CONSOLE" && <AdminConsoleView onBack={goBack} />}
          {route.view === "RTS_LOOKUP" && (
            <RTSView
              initialRefillId={route.refillId}
              onBack={goBack}
            />
          )}
          {route.view === "RTS_HIST" && <RTSHistView onBack={goBack} page={route.page || 1} onTotalPages={setCurrentTotalPages} />}
          {route.view === "WORKER_DASHBOARD" && <WorkerDashboardView onBack={goBack} />}
          {route.view === "PROVIDER_INFO" && <ProviderInfoView onBack={goBack} />}
          {route.view === "AUDIT_LOG" && <AuditLogView onBack={goBack} page={route.page || 1} onTotalPages={setCurrentTotalPages} />}
          {route.view === "SHIPMENT" && (
            <ShipmentView
              onBack={goBack}
              keyCmd={shipmentKeyCmd}
              onKeyCmdHandled={() => setShipmentKeyCmd(null)}
            />
          )}
          {route.view === "SHIPMENT_HIST" && (
            <ShipmentHistView onBack={goBack} page={route.page || 1} onTotalPages={setCurrentTotalPages} />
          )}
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
          </>)}
          </Suspense>
        </div>
        {!showLoginModal && route.view !== "HOME" && showHelp && (() => {
          const hints = getViewHints(route.view, deletePendingPid, currentTotalPages, ("page" in route ? route.page : undefined) || 1);
          return (
            <div
              style={{
                padding: "0.5rem 0.75rem",
                borderTop: "1px solid var(--border, #333)",
                display: "flex",
                gap: "1.5rem",
                flexWrap: "wrap",
                fontSize: "0.82rem",
                color: "var(--text-light)",
              }}
            >
              {hints.map((h) => (
                <span
                  key={h.key}
                  style={h.danger ? { color: "var(--danger)", fontWeight: 700 } : undefined}
                >
                  <code>{h.key}</code> {h.label}
                </span>
              ))}
            </div>
          );
        })()}
        {!showLoginModal && <CommandBar ref={cmdBarRef} onSubmit={handleCommand} />}
      </div>
      {/* Right sidebar: queue dashboard + notifications */}
      {isAuthenticated && (
        <div style={{ width: "300px", flexShrink: 0, display: "flex", flexDirection: "column", gap: "12px", overflowY: "auto" }}>
          <QueueSidebar />
          <NotificationPanel inline quickCode={quickCode} onDismissQuickCode={clearQuickCode} />
        </div>
      )}
      </div>

    </div>
  );
}

