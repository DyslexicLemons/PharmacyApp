import { useState, useEffect, useRef, useContext, useMemo } from "react";
import { getDrugs, getPrescribers, searchPatients, getPatient, checkConflict as apiCheckConflict } from "@/api";
import { AuthContext } from "@/context/AuthContext";
import { useNotification } from "@/context/NotificationContext";
import NewPatientForm from "./NewPatientForm";
import { translateSig, looksLikeSigCode } from "@/sig_codes";
import type { Drug, Patient, PatientSearchResult, Prescriber } from "@/types";
const DAW_CODES = {
  0: "No product selection indicated (generic substitution allowed)",
  1: "Substitution not allowed by prescriber (brand medically necessary)",
  2: "Patient requested brand",
  3: "Pharmacist selected brand",
  4: "Generic not in stock",
  5: "Brand dispensed because generic not available",
  6: "Override due to state law",
  7: "Brand required by insurance",
  8: "Generic not available in marketplace",
  9: "Other",
};

const API = '/api/v1';

function parseDueInput(raw: string) {
  const str = raw.trim().toLowerCase();
  const now = new Date();

  if (str === "q") {
    const d = new Date(now.getTime() + 15 * 60 * 1000);
    return { date: d, priority: "stat" };
  }

  const match = str.match(/^(\d+(?:\.\d+)?)(m|h|d)$/);
  if (!match) return null;

  const amount = parseFloat(match[1]);
  const unit = match[2];
  let ms = 0;
  if (unit === "m") ms = amount * 60 * 1000;
  else if (unit === "h") ms = amount * 60 * 60 * 1000;
  else if (unit === "d") ms = amount * 24 * 60 * 60 * 1000;

  const maxMs = 7 * 24 * 60 * 60 * 1000;
  if (ms > maxMs) return null;

  return { date: new Date(now.getTime() + ms), priority: null };
}

function formatDueDisplay(date: Date) {
  return date.toLocaleString(undefined, {
    month: "short", day: "numeric", year: "numeric",
    hour: "numeric", minute: "2-digit",
  });
}

function parseScheduleDays(raw: string) {
  const n = parseInt(raw.trim(), 10);
  if (isNaN(n) || n < 1 || n > 30) return null;
  const d = new Date();
  d.setDate(d.getDate() + n);
  return d;
}

function formatScheduledDate(date: Date) {
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

export default function PrescriptionForm({ onBack, patientId }: { onBack?: () => void; patientId?: number }) {
  const { token } = useContext(AuthContext);
  const { addNotification } = useNotification();
  const [step, setStep] = useState(1);
  const [drugs, setDrugs] = useState<Drug[]>([]);
  const [prescribers, setPrescribers] = useState<Prescriber[]>([]);
  const [conflict, setConflict] = useState<{ has_conflict: boolean; active_refills: { id: number; state: string; due_date: string; quantity: number }[]; recent_fills: { id: number; sold_date: string; days_supply: number; quantity: number }[]; message?: string } | null>(null);
  const [dueInput, setDueInput] = useState("");
  const [dueDisplay, setDueDisplay] = useState("");
  const [scheduleMode, setScheduleMode] = useState("now"); // "now" | "scheduled"
  const [scheduleDays, setScheduleDays] = useState("");
  const [scheduledDateDisplay, setScheduledDateDisplay] = useState("");

  // SIG code shorthand state
  const [sigInput, setSigInput] = useState("");
  const [showSigRef, setShowSigRef] = useState(false);

  // Drug search state
  const [drugQuery, setDrugQuery] = useState("");
  const [drugDropdownOpen, setDrugDropdownOpen] = useState(false);
  const drugSearchRef = useRef<HTMLDivElement>(null);

  const filteredDrugs = useMemo(() => {
    if (!drugQuery.trim()) return drugs.slice(0, 20);
    const q = drugQuery.toLowerCase();
    return drugs.filter(d =>
      (typeof d.drug_name === "string" && d.drug_name.toLowerCase().includes(q)) ||
      (typeof d.manufacturer === "string" && d.manufacturer.toLowerCase().includes(q)) ||
      String(d.drug_class).includes(q)
    ).slice(0, 20);
  }, [drugs, drugQuery]);

  // Patient search state (used when no patientId prop)
  const [patientQuery, setPatientQuery] = useState("");
  const [patientSearchResults, setPatientSearchResults] = useState<PatientSearchResult[]>([]);
  const [patientSearchError, setPatientSearchError] = useState("");
  const [selectedPatient, setSelectedPatient] = useState<Patient | null>(null);
  const [showNewPatientForm, setShowNewPatientForm] = useState(false);
  const [newPatientPrefill, setNewPatientPrefill] = useState({ last: "", first: "" });

  const [picture, setPicture] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [expirationEdited, setExpirationEdited] = useState(false);

  const defaultExpiration = (() => {
    const d = new Date();
    d.setFullYear(d.getFullYear() + 1);
    return d.toISOString().split("T")[0];
  })();

  const today = new Date().toISOString().split("T")[0];

  const [form, setForm] = useState({
    drug_id: "",
    prescriber_id: "",
    quantity: "",
    days_supply: "",
    total_refills: "1",
    daw_code: 0,
    priority: "normal",
    date_received: today,
    due_date: "",
    expiration_date: defaultExpiration,
    instructions: "",
  });

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (drugSearchRef.current && !drugSearchRef.current.contains(e.target as Node)) {
        setDrugDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  useEffect(() => {
    if (!token) return;
    getDrugs(token).then((res) => setDrugs(Array.isArray(res) ? res : res.items)).catch(console.error);
    getPrescribers(token).then((res) => setPrescribers(Array.isArray(res) ? res : res.items)).catch(console.error);
    if (patientId) {
      getPatient(patientId, token).then((d) => setSelectedPatient(d as Patient)).catch(console.error);
    }
  }, [patientId, token]);

  const handlePatientSearch = async (e: React.SyntheticEvent<HTMLFormElement>) => {
    e.preventDefault();
    setPatientSearchError("");
    setPatientSearchResults([]);
    try {
      if (!token) return;
      const results = await searchPatients(patientQuery, token);
      if (results.length === 0) {
        const [last = "", first = ""] = patientQuery.split(",").map((s) => s.trim());
        setNewPatientPrefill({ last, first });
        setPatientSearchError("no_match");
      } else if (results.length === 1) {
        setSelectedPatient(results[0] as unknown as Patient);
      } else {
        setPatientSearchResults(results);
      }
    } catch (e) {
      setPatientSearchError((e as Error).message);
    }
  };

  const handlePictureSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => setPicture(reader.result as string);
    reader.readAsDataURL(file);
  };

  const getMaxExpiration = (dateReceived: string) => {
    const d = new Date(dateReceived + "T00:00:00");
    d.setFullYear(d.getFullYear() + 1);
    return d.toISOString().split("T")[0];
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => {
    const target = e.target as HTMLInputElement;
    const { name, value, type, checked } = target;

    if (name === "date_received") {
      const maxExp = getMaxExpiration(value);
      // If user manually edited expiration, keep it but cap at new max; otherwise always sync to 1 year out
      const newExp = expirationEdited && form.expiration_date <= maxExp ? form.expiration_date : maxExp;
      setForm({ ...form, date_received: value, expiration_date: newExp });
      return;
    }

    if (name === "expiration_date" && form.date_received) {
      const maxExp = getMaxExpiration(form.date_received);
      if (value > maxExp) {
        addNotification(`Expiration date cannot exceed 1 year from date received (max: ${maxExp}). Date has been capped.`, "warning");
      }
      const capped = value > maxExp ? maxExp : value;
      setExpirationEdited(true);
      setForm({ ...form, expiration_date: capped });
      return;
    }

    const parsed = name === "daw_code" ? parseInt(value, 10) : (type === "checkbox" ? checked : value);
    setForm({ ...form, [name]: parsed });
  };

  const checkConflict = async () => {
    if (!selectedPatient || !form.drug_id) {
      addNotification("Please select patient and drug first", "warning");
      return;
    }
    try {
      if (!token) return;
      const data = await apiCheckConflict(selectedPatient.id, parseInt(String(form.drug_id), 10), token);
      setConflict(data);
      if (data.has_conflict) {
        addNotification(`Conflict: ${data.message} — Review below and continue if intended.`, "warning");
      } else {
        setStep(2);
      }
    } catch (e) {
      addNotification((e as Error).message, "error");
    }
  };

  const handleSubmit = async (initialState: string) => {
    if (!selectedPatient || !token) return;
    try {
      const res = await fetch(`${API}/refills/create_manual`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` },
        body: JSON.stringify({
          patient_id: selectedPatient.id,
          drug_id: parseInt(form.drug_id),
          prescriber_id: parseInt(form.prescriber_id),
          quantity: parseInt(form.quantity),
          days_supply: parseInt(form.days_supply),
          total_refills: parseInt(form.total_refills),
          daw_code: form.daw_code,
          priority: form.priority,
          initial_state: initialState,
          date_received: form.date_received || null,
          due_date: form.due_date || null,
          expiration_date: form.expiration_date || null,
          instructions: form.instructions,
          picture: picture || null,
        }),
      });

      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || "Failed to create prescription");
      }

      const result = await res.json();
      addNotification(`Prescription created successfully! RX#: ${result["RX#"]} | State: ${result.state}`, "success");
      if (onBack) onBack();
    } catch (e) {
      addNotification((e as Error).message, "error");
    }
  };

  const selectedDrug = drugs.find(d => d.id === parseInt(form.drug_id));
  const selectedPrescriber = prescribers.find(p => p.id === parseInt(form.prescriber_id));

  const missingFields = [
    !form.prescriber_id && "Prescriber",
    !form.quantity && "Quantity",
    !form.days_supply && "Days Supply",
    !form.instructions.trim() && "Instructions",
  ].filter(Boolean);

  return (
    <div className="vstack">
      <h2>Create New Prescription</h2>

      {step === 1 && (
        <div className="vstack" style={{ gap: "1rem" }}>
          <h3>Step 1: Select Patient & Drug</h3>

          {/* Patient section */}
          <div className="card" style={{ padding: "1rem" }}>
            <strong>Patient</strong>

            {showNewPatientForm ? (
              <div style={{ marginTop: "0.5rem" }}>
                <NewPatientForm
                  prefillLast={newPatientPrefill.last}
                  prefillFirst={newPatientPrefill.first}
                  onBack={() => { setShowNewPatientForm(false); setPatientSearchError(""); }}
                  onCreated={(patient) => {
                    setSelectedPatient(patient);
                    setShowNewPatientForm(false);
                    setPatientSearchError("");
                    setPatientQuery("");
                  }}
                />
              </div>
            ) : selectedPatient ? (
              <div style={{ marginTop: "0.5rem" }}>
                <div style={{ padding: "0.5rem", background: "var(--bg-light)", borderRadius: "4px" }}>
                  <strong>{selectedPatient.last_name.toUpperCase()}, {selectedPatient.first_name.toUpperCase()}</strong>
                  <div style={{ fontSize: "0.9rem", color: "var(--text-light)" }}>
                    DOB: {selectedPatient.dob} | {selectedPatient.address}
                  </div>
                </div>
                {!patientId && (
                  <button
                    className="btn btn-secondary"
                    style={{ marginTop: "0.5rem" }}
                    onClick={() => { setSelectedPatient(null); setPatientSearchResults([]); setPatientQuery(""); }}
                  >
                    Change Patient
                  </button>
                )}
              </div>
            ) : (
              <div style={{ marginTop: "0.5rem" }}>
                <form onSubmit={handlePatientSearch} style={{ display: "flex", gap: "0.5rem" }}>
                  <input
                    autoFocus
                    className="input"
                    placeholder="Search: Last, First"
                    value={patientQuery}
                    onChange={(e) => setPatientQuery(e.target.value)}
                    style={{ flex: 1 }}
                  />
                  <button className="btn btn-primary" type="submit">Search</button>
                </form>

                {patientSearchError === "no_match" && (
                  <div style={{ marginTop: "0.75rem" }}>
                    <div style={{ color: "var(--text-light)", fontSize: "0.9rem", marginBottom: "0.5rem" }}>
                      No matches for <strong>"{patientQuery}"</strong>. Create a new patient?
                    </div>
                    <div style={{ display: "flex", gap: "0.5rem" }}>
                      <button
                        className="btn btn-primary"
                        onClick={() => setShowNewPatientForm(true)}
                      >
                        Yes, Create Patient
                      </button>
                      <button
                        className="btn btn-secondary"
                        onClick={() => { setPatientSearchError(""); setPatientQuery(""); }}
                      >
                        No
                      </button>
                    </div>
                  </div>
                )}

                {patientSearchError && patientSearchError !== "no_match" && (
                  <div style={{ color: "var(--danger)", marginTop: "0.5rem", fontSize: "0.9rem" }}>
                    {patientSearchError}
                  </div>
                )}

                {patientSearchResults.length > 1 && (
                  <div style={{ marginTop: "0.5rem" }}>
                    <div style={{ fontSize: "0.9rem", color: "var(--text-light)", marginBottom: "0.25rem" }}>
                      Multiple matches — select one:
                    </div>
                    {patientSearchResults.map(p => (
                      <button
                        key={p.id}
                        className="btn btn-secondary"
                        style={{ display: "block", width: "100%", textAlign: "left", marginBottom: "0.25rem" }}
                        onClick={() => { setSelectedPatient(p as unknown as Patient); setPatientSearchResults([]); }}
                      >
                        {p.last_name.toUpperCase()}, {p.first_name.toUpperCase()} — DOB: {p.dob}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Drug section */}
          <div className="card" style={{ padding: "1rem" }}>
            <strong>Drug</strong>

            {selectedDrug ? (
              <div style={{ marginTop: "0.5rem" }}>
                <div style={{ padding: "0.5rem", background: "var(--bg-light)", borderRadius: "4px" }}>
                  <strong>{selectedDrug.drug_name}</strong> ({selectedDrug.manufacturer})
                  {selectedDrug.description && (
                    <div style={{ fontSize: "0.9rem", color: "var(--text-light)", marginTop: "0.25rem" }}>
                      {selectedDrug.description}
                    </div>
                  )}
                  <div style={{ fontSize: "0.9rem", marginTop: "0.25rem" }}>
                    Cost: ${Number(selectedDrug.cost).toFixed(2)} | Class: {selectedDrug.drug_class}
                    {selectedDrug.niosh && <span style={{ color: "var(--danger)", marginLeft: "0.5rem" }}>⚠️ NIOSH HAZARDOUS</span>}
                  </div>
                </div>
                <button
                  className="btn btn-secondary"
                  style={{ marginTop: "0.5rem" }}
                  onClick={() => { setForm(f => ({ ...f, drug_id: "" })); setDrugQuery(""); }}
                >
                  Change Drug
                </button>
              </div>
            ) : (
              <div ref={drugSearchRef} style={{ position: "relative", marginTop: "0.25rem" }}>
                <input
                  className="input"
                  placeholder="Search by name, manufacturer, or class..."
                  value={drugQuery}
                  onChange={(e) => { setDrugQuery(e.target.value); setDrugDropdownOpen(true); }}
                  onFocus={() => setDrugDropdownOpen(true)}
                  style={{ width: "100%", padding: "0.5rem" }}
                />
                {drugDropdownOpen && filteredDrugs.length > 0 && (
                  <div style={{
                    position: "absolute", zIndex: 100, width: "100%",
                    background: "var(--bg, #1e1e2e)", border: "1px solid var(--border, #dee2e6)",
                    borderRadius: "4px", maxHeight: "260px", overflowY: "auto", boxShadow: "0 4px 12px rgba(0,0,0,0.3)",
                  }}>
                    {filteredDrugs.map(d => (
                      <button
                        key={d.id}
                        type="button"
                        style={{
                          display: "block", width: "100%", textAlign: "left",
                          padding: "0.5rem 0.75rem", background: "none", border: "none",
                          borderBottom: "1px solid var(--border, #dee2e6)", cursor: "pointer",
                          color: "#ffffff",
                        }}
                        onMouseEnter={e => (e.currentTarget.style.background = "var(--bg-light)")}
                        onMouseLeave={e => (e.currentTarget.style.background = "none")}
                        onClick={() => {
                          setForm(f => ({ ...f, drug_id: String(d.id) }));
                          setDrugQuery(d.drug_name);
                          setDrugDropdownOpen(false);
                        }}
                      >
                        <span style={{ fontWeight: 500 }}>{d.drug_name}</span>
                        <span style={{ fontSize: "0.85rem", color: "rgba(255,255,255,0.65)", marginLeft: "0.5rem" }}>
                          ({d.manufacturer}) — ${Number(d.cost).toFixed(2)}
                        </span>
                        {d.niosh && <span style={{ color: "var(--danger)", fontSize: "0.8rem", marginLeft: "0.5rem" }}>⚠️ NIOSH</span>}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

          </div>

          {conflict && (
            <div className="card" style={{
              padding: "1rem",
              background: conflict.has_conflict ? "rgba(239, 71, 111, 0.1)" : "rgba(6, 214, 160, 0.1)",
              border: `2px solid ${conflict.has_conflict ? "var(--danger)" : "var(--success)"}`
            }}>
              <h4 style={{ marginTop: 0 }}>Conflict Check Result</h4>
              <p>{conflict.message}</p>
              {conflict.active_refills.length > 0 && (
                <div>
                  <strong>Active Refills:</strong>
                  <ul>
                    {conflict.active_refills.map(r => (
                      <li key={r.id}>
                        ID {r.id}: {r.state} - Due {r.due_date} (Qty: {r.quantity})
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {conflict.has_conflict && (
                <button
                  className="btn btn-warning"
                  style={{ marginTop: "0.5rem" }}
                  onClick={() => setStep(2)}
                >
                  Continue Anyway →
                </button>
              )}
            </div>
          )}

          <button
            className="btn btn-primary"
            onClick={checkConflict}
            disabled={!selectedPatient || !form.drug_id}
          >
            Check for Conflicts & Continue →
          </button>
        </div>
      )}

      {step === 2 && (
        <div className="vstack" style={{ gap: "1rem" }}>
          <h3>Step 2: Prescription Details</h3>

          {selectedPatient && (
            <div style={{ padding: "0.5rem 1rem", background: "var(--bg-light)", borderRadius: "4px", fontSize: "0.9rem" }}>
              Patient: <strong>{selectedPatient.last_name.toUpperCase()}, {selectedPatient.first_name.toUpperCase()}</strong> | Drug: <strong>{selectedDrug?.drug_name}</strong>
            </div>
          )}

          <div className="card" style={{ padding: "1rem" }}>
            <label>
              <strong>Prescriber</strong>
              <select
                name="prescriber_id"
                value={form.prescriber_id}
                onChange={handleChange}
                style={{ width: "100%", padding: "0.5rem", marginTop: "0.25rem" }}
                required
              >
                <option value="">-- Select Prescriber --</option>
                {prescribers.map(p => (
                  <option key={p.id} value={p.id}>
                    Dr. {p.first_name} {p.last_name} (NPI: {p.npi})
                  </option>
                ))}
              </select>
            </label>

            {selectedPrescriber && (
              <div style={{ marginTop: "0.5rem", fontSize: "0.9rem", color: "var(--text-light)" }}>
                {selectedPrescriber.phone_number} | {selectedPrescriber.address}
              </div>
            )}
          </div>

          {/* Dates */}
          <div className="card" style={{ padding: "1rem", display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
            <label>
              <strong>Date Received</strong>
              <input
                type="date"
                name="date_received"
                value={form.date_received}
                onChange={handleChange}
                style={{ width: "100%", padding: "0.5rem", marginTop: "0.25rem" }}
              />
            </label>

            <label>
              <strong>Script Expiration Date</strong>
              <input
                type="date"
                name="expiration_date"
                value={form.expiration_date}
                onChange={handleChange}
                style={{ width: "100%", padding: "0.5rem", marginTop: "0.25rem" }}
              />
            </label>
          </div>

          {/* DAW Code */}
          <div className="card" style={{ padding: "1rem" }}>
            <label>
              <strong>DAW Code</strong>
              <select
                name="daw_code"
                value={form.daw_code}
                onChange={handleChange}
                style={{ width: "100%", padding: "0.5rem", marginTop: "0.25rem" }}
              >
                {Object.entries(DAW_CODES).map(([code, desc]) => (
                  <option key={code} value={code}>{code} — {desc}</option>
                ))}
              </select>
            </label>
          </div>

          {/* Quantity / Days Supply / Total Refills */}
          <div className="card" style={{ padding: "1rem", display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "1rem" }}>
            <label>
              <strong>Quantity</strong>
              <input
                type="number"
                name="quantity"
                value={form.quantity}
                onChange={handleChange}
                min="1"
                required
                style={{ width: "100%", padding: "0.5rem", marginTop: "0.25rem" }}
              />
            </label>

            <label>
              <strong>Days Supply</strong>
              <input
                type="number"
                name="days_supply"
                value={form.days_supply}
                onChange={handleChange}
                min="1"
                required
                style={{ width: "100%", padding: "0.5rem", marginTop: "0.25rem" }}
              />
            </label>

            <label>
              <strong>Total Refills</strong>
              <input
                type="number"
                name="total_refills"
                value={form.total_refills}
                onChange={handleChange}
                min="1"
                style={{ width: "100%", padding: "0.5rem", marginTop: "0.25rem" }}
              />
            </label>
          </div>

          {/* Instructions + Priority */}
          <div className="card" style={{ padding: "1rem" }}>

            {/* SIG Code shorthand panel */}
            <div style={{ marginBottom: "0.75rem" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.35rem" }}>
                <strong style={{ fontSize: "0.9rem" }}>SIG Code Shorthand</strong>
                <button
                  type="button"
                  style={{
                    fontSize: "0.75rem", padding: "0.1rem 0.4rem",
                    background: "none", border: "1px solid var(--border, #dee2e6)",
                    borderRadius: "4px", cursor: "pointer", color: "var(--text-light)",
                  }}
                  onClick={() => setShowSigRef(r => !r)}
                >
                  {showSigRef ? "Hide reference" : "Show codes"}
                </button>
              </div>

              {showSigRef && (
                <div style={{
                  fontSize: "0.75rem", padding: "0.5rem", marginBottom: "0.5rem",
                  background: "var(--bg-light)", borderRadius: "4px",
                  display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(170px, 1fr))", gap: "0.2rem 1rem",
                  maxHeight: "180px", overflowY: "auto",
                }}>
                  {[
                    ["TAB / CAP / GTT / PF", "tablet / capsule / drop / puff"],
                    ["TSP / TBL / SUPP", "teaspoon / tablespoon / suppository"],
                    ["APL / SS", "applicatorful / one-half"],
                    ["PO / SL / INJ / I / APP", "by mouth / under tongue / inject / inhale / apply"],
                    ["OD / OS / AU / OU / IEN", "right eye / left eye / each ear / each eye / nostril"],
                    ["QD / BID / TID / QID", "once daily / twice / 3× / 4× daily"],
                    ["Q4H / Q6H / Q8H / Q12H", "every 4 / 6 / 8 / 12 hours"],
                    ["HS / QAM / QPM / PRN", "bedtime / morning / evening / as needed"],
                    ["STAT / Q2D / Q2-3H", "immediately / every other day / 2–3h"],
                    ["CC / CF / PC / AC", "with meals / with food / after meals / before meals"],
                    ["UF / SW / CR / SP", "until finished / shake well / crushed / sparingly"],
                    ["PA / FE / SB / HD", "for pain / fever / shortness of breath / headache"],
                    ["DI / CON / INF / RA / AR", "diarrhea / constipation / inflammation / rash / arthritis"],
                  ].map(([codes, desc]) => (
                    <div key={codes}>
                      <span style={{ fontWeight: 600, color: "var(--primary, #6c63ff)" }}>{codes}</span>
                      <span style={{ color: "var(--text-light)", marginLeft: "0.3rem" }}>— {desc}</span>
                    </div>
                  ))}
                </div>
              )}

              <div style={{ display: "flex", gap: "0.5rem", alignItems: "flex-start" }}>
                <div style={{ flex: 1 }}>
                  <input
                    className="input"
                    placeholder="e.g.  1 TAB PO QD CF   or   2 GTT OD QID PRN PA"
                    value={sigInput}
                    onChange={e => setSigInput(e.target.value)}
                    style={{ width: "100%", padding: "0.4rem 0.5rem", fontFamily: "monospace" }}
                  />
                  {looksLikeSigCode(sigInput) && (
                    <div style={{
                      marginTop: "0.3rem", padding: "0.35rem 0.6rem",
                      background: "rgba(108, 99, 255, 0.08)", borderRadius: "4px",
                      fontSize: "0.875rem", color: "var(--text)",
                      borderLeft: "3px solid var(--primary, #6c63ff)",
                    }}>
                      {translateSig(sigInput, selectedDrug?.drug_form)}
                    </div>
                  )}
                </div>
                <button
                  type="button"
                  className="btn btn-secondary"
                  style={{ whiteSpace: "nowrap", padding: "0.4rem 0.75rem" }}
                  disabled={!looksLikeSigCode(sigInput)}
                  onClick={() => {
                    const translated = translateSig(sigInput, selectedDrug?.drug_form);
                    if (translated) {
                      setForm(f => ({ ...f, instructions: translated }));
                      setSigInput("");
                    }
                  }}
                >
                  → Apply
                </button>
              </div>
            </div>

            <label>
              <strong>Instructions <span style={{ color: "var(--danger)" }}>*</span></strong>
              <textarea
                name="instructions"
                value={form.instructions}
                onChange={handleChange}
                required
                rows={3}
                placeholder="e.g. Take 1 tablet by mouth once daily with food"
                style={{ width: "100%", padding: "0.5rem", marginTop: "0.25rem", resize: "vertical" }}
              />
            </label>

            <label style={{ marginTop: "0.75rem", display: "block" }}>
              <strong>Priority</strong>
              <select
                name="priority"
                value={form.priority}
                onChange={handleChange}
                style={{ width: "100%", padding: "0.5rem", marginTop: "0.25rem" }}
              >
                <option value="normal">Normal</option>
                <option value="high">High</option>
                <option value="stat">Stat</option>
              </select>
            </label>
          </div>

          {/* Schedule */}
          <div className="card" style={{ padding: "1rem" }}>
            <strong>Schedule</strong>
            <div style={{ display: "flex", gap: "1.5rem", marginTop: "0.5rem" }}>
              <label style={{ display: "flex", alignItems: "center", gap: "0.4rem", cursor: "pointer" }}>
                <input
                  type="radio"
                  name="scheduleMode"
                  value="now"
                  checked={scheduleMode === "now"}
                  onChange={() => {
                    setScheduleMode("now");
                    setScheduledDateDisplay("");
                    setScheduleDays("");
                    setForm(f => ({ ...f, due_date: "" }));
                  }}
                />
                Fill Now
              </label>
              <label style={{ display: "flex", alignItems: "center", gap: "0.4rem", cursor: "pointer" }}>
                <input
                  type="radio"
                  name="scheduleMode"
                  value="scheduled"
                  checked={scheduleMode === "scheduled"}
                  onChange={() => {
                    setScheduleMode("scheduled");
                    setDueInput("");
                    setDueDisplay("");
                    setForm(f => ({ ...f, due_date: "", priority: f.priority === "stat" ? "normal" : f.priority }));
                  }}
                />
                Scheduled
              </label>
            </div>

            {scheduleMode === "now" && (
              <>
                <div style={{ marginTop: "0.5rem", fontSize: "0.85rem", color: "var(--text-light)" }}>
                  Type a shorthand to set when this should be filled:
                  <span style={{ marginLeft: "0.5rem" }}>
                    <code>30m</code> = 30 min &nbsp;|&nbsp;
                    <code>1h</code> = 1 hour &nbsp;|&nbsp;
                    <code>1d</code> = 1 day &nbsp;|&nbsp;
                    <code>q</code> = 15 min + Stat priority &nbsp;(max 7d)
                  </span>
                </div>
                <div style={{ display: "flex", gap: "0.75rem", alignItems: "center", marginTop: "0.5rem" }}>
                  <input
                    className="input"
                    placeholder="e.g. 1h, 30m, q, 1d"
                    value={dueInput}
                    onChange={(e) => {
                      const raw = e.target.value;
                      setDueInput(raw);
                      if (raw.trim() === "") {
                        setDueDisplay("");
                        setForm(f => ({ ...f, due_date: "", priority: f.priority === "stat" ? "normal" : f.priority }));
                        return;
                      }
                      const parsed = parseDueInput(raw);
                      if (parsed) {
                        setDueDisplay(formatDueDisplay(parsed.date));
                        setForm(f => ({
                          ...f,
                          due_date: parsed.date.toISOString(),
                          ...(parsed.priority ? { priority: parsed.priority } : {}),
                        }));
                      } else {
                        setDueDisplay("Invalid — max 7d (e.g. 30m, 2h, 1d)");
                        setForm(f => ({ ...f, due_date: "" }));
                      }
                    }}
                    style={{ width: "120px", padding: "0.5rem" }}
                  />
                  {dueDisplay && (
                    <span style={{
                      fontSize: "0.9rem",
                      color: dueDisplay.startsWith("Invalid") ? "var(--danger)" : "var(--success, #06d6a0)",
                      fontWeight: 500,
                    }}>
                      {dueDisplay.startsWith("Invalid") ? dueDisplay : `→ ${dueDisplay}`}
                    </span>
                  )}
                </div>
              </>
            )}

            {scheduleMode === "scheduled" && (
              <>
                <div style={{ marginTop: "0.5rem", fontSize: "0.85rem", color: "var(--text-light)" }}>
                  Enter how many days out to schedule this fill (1–30 days):
                </div>
                <div style={{ display: "flex", gap: "0.75rem", alignItems: "center", marginTop: "0.5rem" }}>
                  <input
                    className="input"
                    type="number"
                    min="1"
                    max="30"
                    placeholder="e.g. 7"
                    value={scheduleDays}
                    onChange={(e) => {
                      const raw = e.target.value;
                      setScheduleDays(raw);
                      if (raw.trim() === "") {
                        setScheduledDateDisplay("");
                        setForm(f => ({ ...f, due_date: "" }));
                        return;
                      }
                      const d = parseScheduleDays(raw);
                      if (d) {
                        setScheduledDateDisplay(formatScheduledDate(d));
                        setForm(f => ({ ...f, due_date: d.toISOString().split("T")[0] }));
                      } else {
                        setScheduledDateDisplay("Invalid — enter 1–30 days");
                        setForm(f => ({ ...f, due_date: "" }));
                      }
                    }}
                    style={{ width: "120px", padding: "0.5rem" }}
                  />
                  {scheduledDateDisplay && (
                    <span style={{
                      fontSize: "0.9rem",
                      color: scheduledDateDisplay.startsWith("Invalid") ? "var(--danger)" : "var(--success, #06d6a0)",
                      fontWeight: 500,
                    }}>
                      {scheduledDateDisplay.startsWith("Invalid") ? scheduledDateDisplay : `→ ${scheduledDateDisplay}`}
                    </span>
                  )}
                </div>
              </>
            )}
          </div>

          <div className="card" style={{ padding: "1rem" }}>
            <div className="hstack" style={{ justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem" }}>
              <strong>Prescription Image <span style={{ fontWeight: 400, color: "var(--text-light)" }}>(optional)</span></strong>
              <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/*"
                  style={{ display: "none" }}
                  onChange={handlePictureSelect}
                />
                <button
                  type="button"
                  className="btn btn-primary"
                  style={{ padding: "4px 14px", fontSize: "0.85rem" }}
                  onClick={() => fileInputRef.current?.click()}
                >
                  {picture ? "Replace Image" : "+ Upload Image"}
                </button>
                {picture && (
                  <button
                    type="button"
                    className="btn btn-secondary"
                    style={{ padding: "4px 14px", fontSize: "0.85rem" }}
                    onClick={() => { setPicture(null); if (fileInputRef.current) fileInputRef.current.value = ""; }}
                  >
                    Remove
                  </button>
                )}
              </div>
            </div>
            {picture ? (
              <img
                src={picture}
                alt="Prescription"
                style={{ maxWidth: "100%", maxHeight: "300px", objectFit: "contain", borderRadius: "6px", border: "1px solid var(--border, #dee2e6)" }}
              />
            ) : (
              <div style={{
                display: "flex", alignItems: "center", justifyContent: "center",
                height: "120px", border: "2px dashed var(--border, #dee2e6)",
                borderRadius: "6px", color: "var(--text-light)", fontSize: "0.95rem"
              }}>
                No Image Attached
              </div>
            )}
          </div>

          {missingFields.length > 0 && (
            <div style={{
              padding: "0.75rem 1rem",
              background: "rgba(239, 71, 111, 0.1)",
              border: "1px solid var(--danger)",
              borderRadius: "4px",
              fontSize: "0.9rem",
              color: "var(--danger)",
            }}>
              <strong>Required fields missing:</strong> {missingFields.join(", ")}
            </div>
          )}

          <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap", alignItems: "center" }}>
            <button className="btn btn-secondary" onClick={() => setStep(1)}>
              ← Back
            </button>
            {scheduleMode === "now" ? (
              <>
                <button
                  className="btn btn-success"
                  onClick={() => handleSubmit("QV1")}
                  disabled={!form.prescriber_id || !form.quantity || !form.days_supply || !form.instructions.trim()}
                >
                  Create Prescription
                </button>
                <button
                  className="btn btn-warning"
                  onClick={() => handleSubmit("HOLD")}
                  disabled={!form.prescriber_id || !form.quantity || !form.days_supply || !form.instructions.trim()}
                >
                  Put on Hold
                </button>
              </>
            ) : (
              <>
                <button
                  className="btn btn-primary"
                  onClick={() => handleSubmit("SCHEDULED")}
                  disabled={!form.prescriber_id || !form.quantity || !form.days_supply || !form.instructions.trim() || !form.due_date}
                >
                  Schedule Fill
                </button>
                <button
                  className="btn btn-warning"
                  onClick={() => handleSubmit("HOLD")}
                  disabled={!form.prescriber_id || !form.quantity || !form.days_supply || !form.instructions.trim()}
                >
                  Put on Hold
                </button>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
