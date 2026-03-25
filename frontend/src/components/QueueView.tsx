import React, { useContext, useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Badge from "@/components/Badge";
import { fetchQueue } from "@/api";
import { AuthContext } from "@/context/AuthContext";


const PAGE_SIZE = 15;

const PRIORITY_ORDER = { stat: 0, high: 1, normal: 2 };

import type { Refill } from "@/types";

function getSortValue(r: Refill, key: string): string | number {
  switch (key) {
    case "rx":       return r.prescription?.id ?? 0;
    case "drug":     return r.drug.drug_name.toLowerCase();
    case "patient":  return `${r.patient.last_name} ${r.patient.first_name}`.toLowerCase();
    case "qty":      return r.quantity;
    case "days":     return r.days_supply;
    case "cost":     return Number(r.total_cost);
    case "due":      return r.due_date ? new Date(r.due_date).getTime() : 0;
    case "priority": return (PRIORITY_ORDER as Record<string, number>)[r.priority ?? ""] ?? 99;
    case "state":    return r.state;
    default:         return 0;
  }
}

interface QueueViewProps {
  stateFilter?: string;
  onBack?: () => void;
  onSelectRow?: number | null;
  page?: number;
  onSelectRefill?: (id: number) => void;
  onTotalPages?: (n: number) => void;
}

export default function QueueView({ stateFilter, onBack, onSelectRow, page = 1, onSelectRefill, onTotalPages }: QueueViewProps) {
  const { token } = useContext(AuthContext);
  const [sortKey, setSortKey] = useState("due");
  const [sortDir, setSortDir] = useState("asc");

  const { data, isLoading: loading, error: queryError } = useQuery({
    queryKey: ["queue", stateFilter, token],
    queryFn: () => fetchQueue(stateFilter && stateFilter !== "ALL" ? stateFilter : null, token!, 1000),
    select: (res) => Array.isArray(res) ? res : res.items,
    refetchInterval: 30_000,
    enabled: !!token,
  });

  const refills = data ?? [];
  const error = queryError?.message ?? "";

  const handleSelectRefill = (id: number) => {
    if (onSelectRefill) onSelectRefill(id);
  };

  // Handle row selection via command bar
  useEffect(() => {
    if (onSelectRow && refills.length > 0) {
      const rowIndex = onSelectRow - 1;
      if (rowIndex >= 0 && rowIndex < refills.length) {
        handleSelectRefill(refills[rowIndex].id);
      }
    }
  }, [onSelectRow, refills]);

  const handleSort = (key: string) => {
    if (sortKey === key) {
      setSortDir(d => d === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  };

  const sortedRefills = [...refills].sort((a, b) => {
    const av = getSortValue(a, sortKey);
    const bv = getSortValue(b, sortKey);
    if (av < bv) return sortDir === "asc" ? -1 : 1;
    if (av > bv) return sortDir === "asc" ? 1 : -1;
    return 0;
  });

  const total = sortedRefills.length;
  const totalPages = Math.ceil(total / PAGE_SIZE) || 1;
  const effectivePage = Math.min(page, totalPages);

  useEffect(() => {
    onTotalPages?.(totalPages);
  }, [totalPages, onTotalPages]);
  const startIdx = (effectivePage - 1) * PAGE_SIZE;
  const endIdx = Math.min(startIdx + PAGE_SIZE, total);
  const pageItems = sortedRefills.slice(startIdx, endIdx);

  const SortTh = ({ label, colKey }: { label: string; colKey: string }) => {
    const active = sortKey === colKey;
    return (
      <th
        onClick={() => handleSort(colKey)}
        style={{ cursor: "pointer", userSelect: "none", whiteSpace: "nowrap" }}
      >
        {label}
        <span style={{ marginLeft: "0.3rem", opacity: active ? 1 : 0.3, fontSize: "0.8em" }}>
          {active && sortDir === "desc" ? "▼" : "▲"}
        </span>
      </th>
    );
  };

  return (
    <div className="vstack">
      <h2>{stateFilter === "ALL" ? "All Refills" : `Queue: ${stateFilter}`}</h2>
      <p style={{ color: "var(--text-light)", fontSize: "0.9rem" }}>
        Click on a row to view details and take action
      </p>
      {loading ? (
        <p>Loading…</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>#</th>
              <SortTh label="Rx #" colKey="rx" />
              <SortTh label="Drug" colKey="drug" />
              <SortTh label="Patient" colKey="patient" />
              <SortTh label="Qty" colKey="qty" />
              <SortTh label="Days" colKey="days" />
              <SortTh label="Cost" colKey="cost" />
              <SortTh label="Due" colKey="due" />
              <SortTh label="Priority" colKey="priority" />
              <SortTh label="State" colKey="state" />
              {stateFilter === "READY" && <th>Bin</th>}
              {stateFilter === "REJECTED" && <th>Reason</th>}
            </tr>
          </thead>
          <tbody>
            {pageItems.map((r, index) => (
              <tr
                key={r.id}
                onClick={() => handleSelectRefill(r.id)}
                style={{ cursor: "pointer" }}
                className="hover-row"
              >
                <td>
                  <strong style={{ color: "var(--primary)" }}>{startIdx + index + 1}</strong>
                </td>
                <td><strong>{r.prescription?.id}</strong></td>
                <td>
                  <div>
                    <strong>{r.drug.drug_name}</strong>
                    {r.drug.ndc && (
                      <div style={{ fontSize: "0.8rem", color: "var(--text-light)", fontFamily: "monospace" }}>
                        {r.drug.ndc}
                      </div>
                    )}
                    {r.drug.description && (
                      <div style={{ fontSize: "0.85rem", color: "var(--text-light)" }}>
                        {r.drug.description}
                      </div>
                    )}
                  </div>
                </td>
                <td>{r.patient.first_name.toUpperCase()} {r.patient.last_name.toUpperCase()}</td>
                <td>{r.quantity}</td>
                <td>{r.days_supply}</td>
                <td>{"$" + Number(r.total_cost).toFixed(2)}</td>
                <td>{r.due_date ? new Date(r.due_date).toLocaleDateString() : "—"}</td>
                <td>{r.priority}</td>
                <td><Badge state={r.state} /></td>
                {stateFilter === "READY" && (
                  <td>
                    <span className="badge" style={{ background: "var(--success)", color: "white" }}>
                      Bin {r.bin_number}
                    </span>
                  </td>
                )}
                {stateFilter === "REJECTED" && (
                  <td style={{ maxWidth: "300px", fontSize: "0.9rem" }}>
                    {r.rejection_reason}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {!loading && total > 0 && (
        <div style={{ color: "var(--text-light)", fontSize: "0.9rem", marginTop: "0.5rem" }}>
          Showing {startIdx + 1}–{endIdx} of {total}
          {effectivePage > 1 && <span> | [p] prev</span>}
          {endIdx < total && <span> | [n] next</span>}
        </div>
      )}
      {error && <p style={{ color: "#ff7675" }}>{error}</p>}
    </div>
  );
}
