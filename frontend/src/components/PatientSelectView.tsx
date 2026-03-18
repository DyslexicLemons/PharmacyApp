import { useEffect } from "react";
import type { Patient } from "@/types";

/**
 * Shown when a patient search returns multiple matches.
 * The user can click a row or type its number in the command bar.
 *
 * Row highlight rules (requires 3+ chars typed for each name part):
 *   Yellow — first 3 chars of both parts match the patient's names in the typed order
 *   Blue   — first 3 chars match but first/last name order is swapped
 *   None   — near match only (2-char prefix match)
 */

interface PatientSelectViewProps {
  patients: Patient[];
  query: string;
  onSelect: (id: number) => void;
  onSelectRow?: number | null;
}

export default function PatientSelectView({ patients, query, onSelect, onSelectRow }: PatientSelectViewProps) {
  // When a row number comes in from the command bar, fire onSelect
  useEffect(() => {
    if (onSelectRow == null) return;
    const idx = onSelectRow - 1;
    if (idx >= 0 && idx < patients.length) {
      onSelect(patients[idx].id);
    }
  }, [onSelectRow]);

  const parts = query ? query.split(",").map((s) => s.trim().toLowerCase()) : ["", ""];
  const [qa, qb] = parts;
  const qa3 = qa.slice(0, 3);
  const qb3 = qb.slice(0, 3);
  const canHighlight = qa3.length >= 3 && qb3.length >= 3;

  function getRowStyle(p: Patient): React.CSSProperties {
    if (!canHighlight) return { cursor: "pointer" };
    const last = p.last_name.toLowerCase();
    const first = p.first_name.toLowerCase();
    if (last.startsWith(qa3) && first.startsWith(qb3)) {
      return { cursor: "pointer", backgroundColor: "rgba(255, 220, 0, 0.22)" };
    }
    if (last.startsWith(qb3) && first.startsWith(qa3)) {
      return { cursor: "pointer", backgroundColor: "rgba(60, 160, 255, 0.25)" };
    }
    return { cursor: "pointer" };
  }

  const hasYellow = canHighlight && patients.some((p) => {
    const last = p.last_name.toLowerCase();
    const first = p.first_name.toLowerCase();
    return last.startsWith(qa3) && first.startsWith(qb3);
  });
  const hasBlue = canHighlight && patients.some((p) => {
    const last = p.last_name.toLowerCase();
    const first = p.first_name.toLowerCase();
    return last.startsWith(qb3) && first.startsWith(qa3);
  });

  return (
    <div className="vstack">
      <h2>Patient Search: <span style={{ color: "var(--primary)" }}>{query}</span></h2>
      <p style={{ color: "var(--text-light)", marginTop: 0 }}>
        Multiple matches found. Click a row or type its number to open the profile.
      </p>
      {(hasYellow || hasBlue) && (
        <div style={{ display: "flex", gap: "1.2rem", marginBottom: "0.5rem", fontSize: "0.82rem", color: "var(--text-light)" }}>
          {hasYellow && (
            <span>
              <span style={{ display: "inline-block", width: 12, height: 12, backgroundColor: "rgba(255, 220, 0, 0.5)", borderRadius: 2, marginRight: 5, verticalAlign: "middle" }} />
              Strong match
            </span>
          )}
          {hasBlue && (
            <span>
              <span style={{ display: "inline-block", width: 12, height: 12, backgroundColor: "rgba(60, 160, 255, 0.45)", borderRadius: 2, marginRight: 5, verticalAlign: "middle" }} />
              Name order swapped
            </span>
          )}
        </div>
      )}
      <table className="table">
        <thead>
          <tr>
            <th>#</th>
            <th>Last Name</th>
            <th>First Name</th>
            <th>Date of Birth</th>
            <th>Address</th>
          </tr>
        </thead>
        <tbody>
          {patients.map((p, i) => (
            <tr
              key={p.id}
              onClick={() => onSelect(p.id)}
              style={getRowStyle(p)}
              className="hover-row"
            >
              <td><strong style={{ color: "var(--primary)" }}>{i + 1}</strong></td>
              <td>{p.last_name.toUpperCase()}</td>
              <td>{p.first_name.toUpperCase()}</td>
              <td>{new Date(p.dob).toLocaleDateString()}</td>
              <td>{p.address.toUpperCase()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
