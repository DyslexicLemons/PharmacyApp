import React, { useEffect, useState } from "react";

export default function Home({ onCommand }) {
  return (
    <div className="vstack">
      <h1>💊 JoeMed</h1>
      <p style={{ fontSize: "1.1rem", marginBottom: "2rem", color: "var(--text-light)" }}>
        Your trusted pharmacy management system. Type a command below to get started.
      </p>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.5rem" }}>
        {/* Left Column */}
        <div className="vstack" style={{ gap: "1.5rem" }}>
          {/* Workflow Queues */}
          <section className="card vstack" style={{ padding: "1rem" }}>
            <h3 style={{ marginTop: 0, marginBottom: "0.75rem", paddingBottom: "0.5rem" }}>
              📋 Workflow Queues
            </h3>
            <ul style={{ margin: 0 }}>
              <li>
                <code>qt</code> – Queue Triage (external Rx)
              </li>
              <li>
                <code>qv1</code> – Verify 1 (initial approval)
              </li>
              <li>
                <code>qp</code> – Prep/Fill
              </li>
              <li>
                <code>qv2</code> – Final Verify
              </li>
              <li>
                <code>ready</code> – Ready for Pickup
              </li>
              <li>
                <code>hold</code> – On Hold
              </li>
              <li>
                <code>rejected</code> – Rejected
              </li>
              <li>
                <code>all</code> – All active prescriptions
              </li>
            </ul>
          </section>

          {/* Patient & Prescription Management */}
          <section className="card vstack" style={{ padding: "1rem" }}>
            <h3 style={{ marginTop: 0, marginBottom: "0.75rem", paddingBottom: "0.5rem" }}>
              👤 Patients & Prescriptions
            </h3>
            <ul style={{ margin: 0 }}>
              <li>
                <code>pt</code> – View all patients
              </li>
              <li>
                <code>lastname,firstname</code> – Open patient profile (e.g., <code>smith,john</code>)
              </li>
              <li>
                <code>&lt;space&gt;</code> – Create new prescription
              </li>
              <li>
                <code>prescribers</code> – View all prescribers
              </li>
            </ul>
          </section>

          {/* Navigation */}
          <section className="card vstack" style={{ padding: "1rem", background: "linear-gradient(135deg, rgba(0, 180, 216, 0.1) 0%, rgba(0, 100, 148, 0.1) 100%)" }}>
            <h3 style={{ marginTop: 0, marginBottom: "0.75rem", paddingBottom: "0.5rem" }}>
              🧭 Navigation
            </h3>
            <ul style={{ margin: 0 }}>
              <li>
                <code>home</code> – Return to this screen
              </li>
              <li>
                <code>q</code> – Go back to previous screen
              </li>
            </ul>
          </section>
        </div>

        {/* Right Column */}
        <div className="vstack" style={{ gap: "1.5rem" }}>
          {/* Inventory & Catalog */}
          <section className="card vstack" style={{ padding: "1rem" }}>
            <h3 style={{ marginTop: 0, marginBottom: "0.75rem", paddingBottom: "0.5rem" }}>
              💊 Inventory & Catalog
            </h3>
            <ul style={{ margin: 0 }}>
              <li>
                <code>drugs</code> – View drug catalog
              </li>
              <li>
                <code>stock</code> – View current inventory
              </li>
            </ul>
          </section>

          {/* Reports & History */}
          <section className="card vstack" style={{ padding: "1rem" }}>
            <h3 style={{ marginTop: 0, marginBottom: "0.75rem", paddingBottom: "0.5rem" }}>
              📊 Reports & History
            </h3>
            <ul style={{ margin: 0 }}>
              <li>
                <code>refill_hist</code> – View fill history
              </li>
            </ul>
          </section>

          {/* Admin Commands */}
          <section className="card vstack" style={{ padding: "1rem", background: "linear-gradient(135deg, rgba(220, 20, 60, 0.1) 0%, rgba(178, 34, 34, 0.1) 100%)" }}>
            <h3 style={{ marginTop: 0, marginBottom: "0.75rem", paddingBottom: "0.5rem" }}>
              ⚙️ Admin Commands
            </h3>
            <ul style={{ margin: 0 }}>
              <li>
                <code>gen_test</code> – Generate 50 test prescriptions (⚠️ deletes all current data)
              </li>
            </ul>
          </section>
        </div>
      </div>
    </div>
  );
}