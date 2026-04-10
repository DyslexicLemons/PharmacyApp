import React, { useContext, useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Badge from "@/components/Badge";
import { fetchQueue } from "@/api";
import { AuthContext } from "@/context/AuthContext";


const PAGE_SIZE = 15;

import type { Refill } from "@/types";

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
    queryKey: ["queue", stateFilter, token, page, sortKey, sortDir],
    queryFn: () => fetchQueue(
      stateFilter && stateFilter !== "ALL" ? stateFilter : null,
      token!,
      PAGE_SIZE,
      (page - 1) * PAGE_SIZE,
      sortKey,
      sortDir,
    ),
    refetchInterval: 30_000,
    enabled: !!token,
  });

  const pageItems = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.ceil(total / PAGE_SIZE) || 1;
  const startIdx = (page - 1) * PAGE_SIZE;
  const endIdx = Math.min(startIdx + pageItems.length, startIdx + PAGE_SIZE);
  const error = queryError?.message ?? "";

  const handleSelectRefill = (id: number) => {
    if (onSelectRefill) onSelectRefill(id);
  };

  // Handle row selection via command bar
  useEffect(() => {
    if (onSelectRow && pageItems.length > 0) {
      const rowIndex = onSelectRow - 1;
      if (rowIndex >= 0 && rowIndex < pageItems.length) {
        handleSelectRefill(pageItems[rowIndex].id);
      }
    }
  }, [onSelectRow, pageItems]);

  useEffect(() => {
    onTotalPages?.(totalPages);
  }, [totalPages, onTotalPages]);

  const handleSort = (key: string) => {
    if (sortKey === key) {
      setSortDir(d => d === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  };

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
      <h2>{stateFilter === "ALL" ? "All Refills" : `${stateFilter}`}</h2>
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
          {page > 1 && <span> | [p] prev</span>}
          {endIdx < total && <span> | [n] next</span>}
        </div>
      )}
      {error && <p style={{ color: "#ff7675" }}>{error}</p>}
    </div>
  );
}
