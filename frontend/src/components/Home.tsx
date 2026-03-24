interface HomeProps {
  onCommand?: (cmd: string) => void;
}

export default function Home({ onCommand }: HomeProps) {
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
                <code>pt</code> / <code>patients</code> – View all patients
              </li>
              <li>
                <code>lastname,firstname</code> – Open patient profile (e.g., <code>smith,john</code>)
              </li>
              <li>
                <code>&lt;space&gt;</code> – Create new prescription
              </li>
              <li>
                <code>rx&lt;id&gt;</code> – Look up prescription by Rx ID (e.g., <code>rx1701234</code>)
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
              <li>
                <code>n</code> / <code>p</code> – Next / previous page
              </li>
              <li>
                <code>&lt;number&gt;</code> – Select row (in queue or patient select views)
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
                <code>register</code> – Register a new user account
              </li>
              <li>
                <code>users</code> – Manage users (create accounts, assign roles)
              </li>
              <li>
                <code>logs</code> – View audit log
              </li>
              <li>
                <code>settings</code> – System settings (bin count, etc.)
              </li>
              <li>
                <code>admin</code> – Admin console (generate test data, clear prescriptions)
              </li>
              <li>
                <code>workers</code> – Worker dashboard (live station status &amp; queue counts)
              </li>
              <li>
                <code>gen_test</code> – Generate 50 test prescriptions (⚠️ deletes all current data)
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
                <code>stock</code> – View current inventory (includes RTS totals)
              </li>
            </ul>
          </section>

          {/* Shipments */}
          <section className="card vstack" style={{ padding: "1rem" }}>
            <h3 style={{ marginTop: 0, marginBottom: "0.75rem", paddingBottom: "0.5rem" }}>
              📦 Shipments
            </h3>
            <ul style={{ margin: 0 }}>
              <li>
                <code>shipment</code> – Receive a new shipment
              </li>
              <li>
                <code>shipment_hist</code> – View shipment history
              </li>
              <li>
                <code>f</code> / <code>finished</code> – Finish current shipment (in Shipment view)
              </li>
            </ul>
          </section>

          {/* Return to Stock */}
          <section className="card vstack" style={{ padding: "1rem", background: "linear-gradient(135deg, rgba(255, 190, 11, 0.08) 0%, rgba(200, 100, 0, 0.08) 100%)" }}>
            <h3 style={{ marginTop: 0, marginBottom: "0.75rem", paddingBottom: "0.5rem" }}>
              ↩ Return to Stock
            </h3>
            <ul style={{ margin: 0 }}>
              <li>
                <code>rts</code> – Return a READY prescription to stock
              </li>
              <li>
                <code>rts&lt;id&gt;</code> – RTS a specific refill (e.g., <code>rts1042</code>)
              </li>
              <li>
                <code>rts_hist</code> – View all return-to-stock history
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

          {/* Context-Specific Commands */}
          <section className="card vstack" style={{ padding: "1rem", background: "linear-gradient(135deg, rgba(255, 190, 11, 0.08) 0%, rgba(200, 130, 0, 0.08) 100%)" }}>
            <h3 style={{ marginTop: 0, marginBottom: "0.75rem", paddingBottom: "0.5rem" }}>
              🔍 Context Commands
            </h3>
            <ul style={{ margin: 0 }}>
              <li>
                <code>&lt;num&gt;</code> – View prescription by row (in Patient profile)
              </li>
              <li>
                <code>e</code> – Edit refill (in Refill Detail)
              </li>
              <li>
                <code>a</code> – Approve refill (in Refill Detail)
              </li>
              <li>
                <code>h</code> – Hold refill (in Refill Detail)
              </li>
            </ul>
          </section>

          {/* System */}
          <section className="card vstack" style={{ padding: "1rem" }}>
            <h3 style={{ marginTop: 0, marginBottom: "0.75rem", paddingBottom: "0.5rem" }}>
              🖥️ System
            </h3>
            <ul style={{ margin: 0 }}>
              <li>
                <code>?</code> – Toggle this help panel
              </li>
              <li>
                <code>logout</code> – Log out of the session
              </li>
            </ul>
          </section>
        </div>
      </div>
    </div>
  );
}
