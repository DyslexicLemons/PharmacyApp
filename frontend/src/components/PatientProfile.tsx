import { useContext, useEffect, useState } from "react";
import { getPatient } from "@/api";
import { AuthContext } from "@/context/AuthContext";
import Badge from "@/components/Badge";

const PAGE_SIZE = 15;

interface LatestRefill {
  quantity: number;
  days_supply: number;
  sold_date?: string | null;
  total_cost?: number | string | null;
  completed_date?: string | null;
  next_pickup?: string | null;
  state?: string | null;
}

interface PrescriptionRow {
  id: number;
  drug: { drug_name: string; ndc?: string | null };
  remaining_quantity: number;
  date_received: string;
  expiration_date?: string | null;
  is_inactive?: boolean;
  is_expired?: boolean;
  latest_refill?: LatestRefill | null;
}

interface PatientData {
  id: number;
  first_name: string;
  last_name: string;
  dob: string;
  address: string;
  city?: string;
  state?: string;
  prescriptions: PrescriptionRow[];
}

interface PatientProfileProps {
  pid: number;
  onBack?: () => void;
  onFill?: (prescription: PrescriptionRow, patient: PatientData) => void;
  onDataLoaded?: (data: PatientData) => void;
  page?: number;
}

export default function PatientProfile({ pid, onBack, onFill, onDataLoaded, page = 1 }: PatientProfileProps) {
  const { token } = useContext(AuthContext);
  const [data, setData] = useState<PatientData | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let mounted = true;

    getPatient(pid, token)
      .then((d: PatientData) => {
        if (!mounted) return;
        setData(d);
        onDataLoaded?.(d);
      })
      .catch((e: Error) => setError(e.message));

    return () => {
      mounted = false;
    };
  }, [pid]);

  if (error) return <p style={{ color: "#ff7675" }}>{error}</p>;
  if (!data) return <p>Loading…</p>;

  const prescriptions = data.prescriptions;
  const total = prescriptions.length;

  const startIdx = (page - 1) * PAGE_SIZE;
  const endIdx = Math.min(startIdx + PAGE_SIZE, total);
  const pageItems = prescriptions.slice(startIdx, endIdx);

  return (
    <div className="vstack">
      <h2>Patient Profile</h2>

      <div className="card vstack">
        <div className="hstack" style={{ justifyContent: "space-between" }}>
          <strong>
            {data.last_name.toUpperCase()}, {data.first_name.toUpperCase()}
          </strong>
          <span>DOB: {new Date(data.dob).toLocaleDateString()}</span>
        </div>
        <div>
          {data.address.toUpperCase()}
          {(data.city || data.state) && (
            <span>, {[data.city, data.state].filter(Boolean).map(s => s!.toUpperCase()).join(", ")}</span>
          )}
        </div>
      </div>

      <h3>Prescriptions</h3>

      {total === 0 ? (
        <p
          style={{
            color: "var(--text-light)",
            textAlign: "center",
            fontSize: "1.4rem",
            marginTop: "2rem",
          }}
        >
          No prescriptions
        </p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>#</th>
              <th>Rx #</th>
              <th>Drug</th>
              <th>Qty Remaining</th>
              <th>Date Received</th>
              <th>Last Qty Dispensed</th>
              <th>Days Supply</th>
              <th>Last Sold</th>
              <th>Last cost</th>
              <th>Last filled</th>
              <th>Expiration</th>
              <th>Current Status</th>
              <th></th>
            </tr>
          </thead>

          <tbody>
            {pageItems.map((r, index) => {
              const BLOCKING_STATES = ["QT", "QV1", "QP", "QV2", "READY"];

              const fillBlocked =
                r.latest_refill &&
                BLOCKING_STATES.includes(r.latest_refill.state ?? "");

              const noQuantityRemaining = r.remaining_quantity <= 0;

              const showFillButton = !fillBlocked && !noQuantityRemaining && !r.is_inactive && !r.is_expired;

              return (
                <tr key={r.id}>
                  <td>
                    <strong style={{ color: "var(--primary)" }}>
                      {startIdx + index + 1}
                    </strong>
                  </td>

                  <td>
                    <strong>{r.id}</strong>
                  </td>

                  <td>
                    <div>{r.drug.drug_name}</div>
                    {r.drug.ndc && (
                      <div style={{ fontSize: "0.8rem", color: "var(--text-light)", fontFamily: "monospace" }}>
                        {r.drug.ndc}
                      </div>
                    )}
                  </td>

                  <td>{r.remaining_quantity}</td>

                  <td>
                    {new Date(r.date_received).toLocaleDateString()}
                  </td>

                  {r.latest_refill ? (
                    <>
                      <td>{r.latest_refill.quantity}</td>

                      <td>{r.latest_refill.days_supply}</td>

                      <td>
                        {r.latest_refill.sold_date
                          ? new Date(r.latest_refill.sold_date).toLocaleDateString()
                          : "—"}
                      </td>

                      <td>
                        {r.latest_refill.total_cost
                          ? "$" + Number(r.latest_refill.total_cost).toFixed(2)
                          : "—"}
                      </td>

                      <td>
                        {r.latest_refill.completed_date
                          ? new Date(r.latest_refill.completed_date).toLocaleDateString()
                          : "—"}
                      </td>

                      <td>
                        {r.expiration_date
                          ? new Date(r.expiration_date).toLocaleDateString()
                          : "—"}
                      </td>

                      <td>
                        {r.is_inactive ? (
                          <Badge state="INACTIVATED" />
                        ) : r.is_expired ? (
                          <Badge state="EXPIRED" />
                        ) : r.latest_refill.next_pickup ? (
                          new Date(r.latest_refill.next_pickup).toLocaleDateString()
                        ) : r.latest_refill.state ? (
                          <Badge state={r.latest_refill.state} />
                        ) : (
                          "—"
                        )}
                      </td>
                    </>
                  ) : (
                    <>
                      <td colSpan={6} style={{ color: "#888" }}>
                        No refills yet
                      </td>
                      <td>
                        {r.is_inactive ? (
                          <Badge state="INACTIVATED" />
                        ) : r.is_expired ? (
                          <Badge state="EXPIRED" />
                        ) : "—"}
                      </td>
                    </>
                  )}

                  <td>
                    {r.is_inactive ? (
                      <span style={{ color: "#6b7280", fontSize: "0.8rem", fontWeight: 600 }}>
                        Inactive
                      </span>
                    ) : r.is_expired ? (
                      <span style={{ color: "#92400e", fontSize: "0.8rem", fontWeight: 600 }}>
                        Expired
                      </span>
                    ) : noQuantityRemaining ? (
                      <span
                        style={{
                          color: "#888",
                          fontSize: "0.8rem",
                        }}
                      >
                        No Refills
                      </span>
                    ) : (
                      onFill &&
                      showFillButton && (
                        <button
                          className="btn btn-primary"
                          style={{
                            padding: "2px 10px",
                            fontSize: "0.8rem",
                          }}
                          onClick={() => onFill(r, data)}
                        >
                          Fill
                        </button>
                      )
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}

      {total > PAGE_SIZE && (
        <div
          style={{
            color: "var(--text-light)",
            fontSize: "0.9rem",
            marginTop: "0.5rem",
          }}
        >
          Showing {startIdx + 1}–{endIdx} of {total}
          {page > 1 && <span> | [p] prev</span>}
          {endIdx < total && <span> | [n] next</span>}
        </div>
      )}
    </div>
  );
}
