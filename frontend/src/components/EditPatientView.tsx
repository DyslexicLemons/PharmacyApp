import React, { useContext, useEffect, useState } from "react";
import { AuthContext } from "@/context/AuthContext";
import {
  getPatient,
  updatePatient,
  getInsuranceCompanies,
  addPatientInsurance,
  deletePatientInsurance,
} from "@/api";
import type { InsuranceCompany } from "@/types";

interface InsuranceSummary {
  id: number;
  is_primary: boolean;
  is_active: boolean;
  member_id: string;
  group_number: string | null;
  insurance_company: { id: number; plan_name: string };
}

interface PatientFull {
  id: number;
  first_name: string;
  last_name: string;
  dob: string;
  address: string;
  city?: string;
  state?: string;
  insurances?: InsuranceSummary[];
}

interface Props {
  pid: number;
  onBack: () => void;
  onSaved: () => void;
}

const UPPERCASE_FIELDS = ["first_name", "last_name", "address", "city", "state"];

export default function EditPatientView({ pid, onBack, onSaved }: Props) {
  const { token } = useContext(AuthContext);

  const [patient, setPatient] = useState<PatientFull | null>(null);
  const [loadError, setLoadError] = useState("");

  // Demographics form
  const [form, setForm] = useState({
    first_name: "",
    last_name: "",
    dob: "",
    address: "",
    city: "",
    state: "",
  });
  const [demoSaving, setDemoSaving] = useState(false);
  const [demoError, setDemoError] = useState("");
  const [demoSuccess, setDemoSuccess] = useState(false);

  // Insurance
  const [insurances, setInsurances] = useState<InsuranceSummary[]>([]);
  const [companies, setCompanies] = useState<InsuranceCompany[]>([]);
  const [insForm, setInsForm] = useState({
    insurance_company_id: "",
    member_id: "",
    group_number: "",
    is_primary: true,
  });
  const [insError, setInsError] = useState("");
  const [insSaving, setInsSaving] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  useEffect(() => {
    if (!token) return;
    Promise.all([
      getPatient(pid, token) as Promise<unknown>,
      getInsuranceCompanies(token),
    ])
      .then(([p, comps]) => {
        const pt = p as PatientFull;
        setPatient(pt);
        setForm({
          first_name: pt.first_name,
          last_name: pt.last_name,
          dob: pt.dob ? pt.dob.slice(0, 10) : "",
          address: pt.address,
          city: pt.city ?? "",
          state: pt.state ?? "",
        });
        setInsurances((pt.insurances ?? []).filter((i) => i.is_active));
        setCompanies(comps);
      })
      .catch((e: Error) => setLoadError(e.message));
  }, [pid, token]);

  function handleDemoChange(e: React.ChangeEvent<HTMLInputElement>) {
    const { name, value } = e.target;
    setForm((prev) => ({
      ...prev,
      [name]: UPPERCASE_FIELDS.includes(name) ? value.toUpperCase() : value,
    }));
  }

  async function handleDemoSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!token) return;
    setDemoError("");
    setDemoSuccess(false);
    setDemoSaving(true);
    try {
      await updatePatient(pid, form as unknown as Record<string, unknown>, token);
      setDemoSuccess(true);
    } catch (err) {
      setDemoError((err as Error).message);
    } finally {
      setDemoSaving(false);
    }
  }

  async function handleAddInsurance(e: React.FormEvent) {
    e.preventDefault();
    if (!token) return;
    setInsError("");
    setInsSaving(true);
    try {
      const created = await addPatientInsurance(
        pid,
        {
          insurance_company_id: parseInt(insForm.insurance_company_id, 10),
          member_id: insForm.member_id.trim(),
          group_number: insForm.group_number.trim() || null,
          is_primary: insForm.is_primary,
        },
        token,
      ) as unknown as InsuranceSummary;
      setInsurances((prev) => {
        const updated = insForm.is_primary
          ? prev.map((i) => ({ ...i, is_primary: false }))
          : prev;
        return [...updated, { ...created, is_active: true }];
      });
      setInsForm({ insurance_company_id: "", member_id: "", group_number: "", is_primary: true });
    } catch (err) {
      setInsError((err as Error).message);
    } finally {
      setInsSaving(false);
    }
  }

  async function handleDeleteInsurance(insuranceId: number) {
    if (!token) return;
    setDeletingId(insuranceId);
    try {
      await deletePatientInsurance(pid, insuranceId, token);
      setInsurances((prev) => prev.filter((i) => i.id !== insuranceId));
    } catch (err) {
      setInsError((err as Error).message);
    } finally {
      setDeletingId(null);
    }
  }

  if (loadError) return <p style={{ color: "#ff7675" }}>{loadError}</p>;
  if (!patient) return <p>Loading…</p>;

  const demoReady =
    form.first_name.trim() &&
    form.last_name.trim() &&
    form.dob &&
    form.address.trim() &&
    form.city.trim() &&
    form.state.trim();

  const insReady = insForm.insurance_company_id && insForm.member_id.trim();

  return (
    <div className="vstack">
      <h2>
        Edit Patient — {patient.last_name.toUpperCase()}, {patient.first_name.toUpperCase()}
      </h2>

      {/* Demographics */}
      <section className="card vstack" style={{ padding: "1rem" }}>
        <h3 style={{ marginTop: 0 }}>Demographics</h3>
        <form onSubmit={handleDemoSubmit}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem", marginBottom: "1rem" }}>
            <label>
              <strong>Last Name <span style={{ color: "var(--danger)" }}>*</span></strong>
              <input
                autoFocus
                className="input"
                name="last_name"
                value={form.last_name}
                onChange={handleDemoChange}
                required
                style={{ width: "100%", padding: "0.5rem", marginTop: "0.25rem" }}
              />
            </label>
            <label>
              <strong>First Name <span style={{ color: "var(--danger)" }}>*</span></strong>
              <input
                className="input"
                name="first_name"
                value={form.first_name}
                onChange={handleDemoChange}
                required
                style={{ width: "100%", padding: "0.5rem", marginTop: "0.25rem" }}
              />
            </label>
            <label>
              <strong>Date of Birth <span style={{ color: "var(--danger)" }}>*</span></strong>
              <input
                type="date"
                className="input"
                name="dob"
                value={form.dob}
                onChange={handleDemoChange}
                required
                style={{ width: "100%", padding: "0.5rem", marginTop: "0.25rem" }}
              />
            </label>
            <label>
              <strong>Address <span style={{ color: "var(--danger)" }}>*</span></strong>
              <input
                className="input"
                name="address"
                value={form.address}
                onChange={handleDemoChange}
                required
                style={{ width: "100%", padding: "0.5rem", marginTop: "0.25rem" }}
              />
            </label>
            <label>
              <strong>City <span style={{ color: "var(--danger)" }}>*</span></strong>
              <input
                className="input"
                name="city"
                value={form.city}
                onChange={handleDemoChange}
                required
                style={{ width: "100%", padding: "0.5rem", marginTop: "0.25rem" }}
              />
            </label>
            <label>
              <strong>State <span style={{ color: "var(--danger)" }}>*</span></strong>
              <input
                className="input"
                name="state"
                value={form.state}
                onChange={handleDemoChange}
                required
                maxLength={2}
                placeholder="e.g. TX"
                style={{ width: "100%", padding: "0.5rem", marginTop: "0.25rem" }}
              />
            </label>
          </div>
          {demoError && <div style={{ color: "var(--danger)", fontSize: "0.9rem", marginBottom: "0.5rem" }}>{demoError}</div>}
          {demoSuccess && <div style={{ color: "var(--success)", fontSize: "0.9rem", marginBottom: "0.5rem" }}>Saved.</div>}
          <button type="submit" className="btn btn-primary" disabled={!demoReady || demoSaving}>
            {demoSaving ? "Saving…" : "Save Demographics"}
          </button>
        </form>
      </section>

      {/* Insurance on file */}
      <section className="card vstack" style={{ padding: "1rem" }}>
        <h3 style={{ marginTop: 0 }}>Insurance on File</h3>

        {insurances.length === 0 ? (
          <p style={{ color: "var(--text-light)", margin: 0 }}>No insurance on file.</p>
        ) : (
          <table className="table" style={{ marginBottom: "1rem" }}>
            <thead>
              <tr>
                <th>Plan</th>
                <th>Member ID</th>
                <th>Group #</th>
                <th>Primary</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {insurances.map((ins) => (
                <tr key={ins.id}>
                  <td>{ins.insurance_company.plan_name}</td>
                  <td style={{ fontFamily: "monospace" }}>{ins.member_id}</td>
                  <td style={{ fontFamily: "monospace" }}>{ins.group_number ?? "—"}</td>
                  <td>{ins.is_primary ? <span style={{ color: "var(--success)", fontWeight: 600 }}>Yes</span> : "No"}</td>
                  <td>
                    <button
                      className="btn btn-secondary"
                      style={{ padding: "2px 10px", fontSize: "0.8rem", color: "var(--danger)", borderColor: "var(--danger)" }}
                      onClick={() => handleDeleteInsurance(ins.id)}
                      disabled={deletingId === ins.id}
                    >
                      {deletingId === ins.id ? "Removing…" : "Remove"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {/* Add insurance form */}
        <h4 style={{ marginBottom: "0.5rem" }}>Add Insurance</h4>
        <form onSubmit={handleAddInsurance}>
          <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr", gap: "0.75rem", marginBottom: "0.75rem" }}>
            <label>
              <strong>Insurance Plan <span style={{ color: "var(--danger)" }}>*</span></strong>
              <select
                className="input"
                value={insForm.insurance_company_id}
                onChange={(e) => setInsForm((p) => ({ ...p, insurance_company_id: e.target.value }))}
                required
                style={{ width: "100%", padding: "0.5rem", marginTop: "0.25rem" }}
              >
                <option value="">— Select plan —</option>
                {companies.map((c) => (
                  <option key={c.id} value={c.id}>{c.plan_name}</option>
                ))}
              </select>
            </label>
            <label>
              <strong>Member ID <span style={{ color: "var(--danger)" }}>*</span></strong>
              <input
                className="input"
                value={insForm.member_id}
                onChange={(e) => setInsForm((p) => ({ ...p, member_id: e.target.value }))}
                required
                style={{ width: "100%", padding: "0.5rem", marginTop: "0.25rem" }}
              />
            </label>
            <label>
              <strong>Group #</strong>
              <input
                className="input"
                value={insForm.group_number}
                onChange={(e) => setInsForm((p) => ({ ...p, group_number: e.target.value }))}
                style={{ width: "100%", padding: "0.5rem", marginTop: "0.25rem" }}
              />
            </label>
          </div>
          <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.75rem" }}>
            <input
              type="checkbox"
              checked={insForm.is_primary}
              onChange={(e) => setInsForm((p) => ({ ...p, is_primary: e.target.checked }))}
            />
            <strong>Set as primary insurance</strong>
          </label>
          {insError && <div style={{ color: "var(--danger)", fontSize: "0.9rem", marginBottom: "0.5rem" }}>{insError}</div>}
          {!insForm.insurance_company_id && (
            <div style={{ color: "var(--text-light)", fontSize: "0.85rem", marginBottom: "0.5rem" }}>
              Select an insurance plan to continue.
            </div>
          )}
          {insForm.insurance_company_id && !insForm.member_id.trim() && (
            <div style={{ color: "var(--text-light)", fontSize: "0.85rem", marginBottom: "0.5rem" }}>
              Enter a member ID to continue.
            </div>
          )}
          <button type="submit" className="btn btn-primary" disabled={!insReady || insSaving}>
            {insSaving ? "Adding…" : "Add Insurance"}
          </button>
        </form>
      </section>

      <div>
        <button className="btn btn-secondary" onClick={onSaved}>
          ← Back to Profile
        </button>
      </div>
    </div>
  );
}
