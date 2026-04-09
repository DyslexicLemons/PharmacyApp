import { useContext, useEffect, useState } from "react";
import { AuthContext } from "@/context/AuthContext";

interface ProviderStatus {
  drug_catalog: string | null;
  insurance_gateway: string | null;
}

interface Props {
  onBack?: () => void;
}

export default function ProviderInfoView({ onBack }: Props) {
  const { token } = useContext(AuthContext);
  const [status, setStatus] = useState<ProviderStatus | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!token) return;
    fetch("/api/v1/providers/status", {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json() as Promise<ProviderStatus>;
      })
      .then(setStatus)
      .catch((e: Error) => setError(e.message));
  }, [token]);

  return (
    <div className="vstack" style={{ maxWidth: 600 }}>
      <div style={{ display: "flex", alignItems: "center", gap: "1rem", marginBottom: "1.5rem" }}>
        <h2 style={{ margin: 0 }}>Provider Info</h2>
        {onBack && (
          <button className="btn btn-secondary" onClick={onBack} style={{ marginLeft: "auto" }}>
            q — back
          </button>
        )}
      </div>

      {error && (
        <div style={{ color: "var(--error, #e63946)", marginBottom: "1rem" }}>{error}</div>
      )}

      {!status && !error && (
        <div style={{ color: "var(--text-light)" }}>Loading…</div>
      )}

      {status && (
        <div className="vstack" style={{ gap: "1rem" }}>
          <section className="card vstack" style={{ padding: "1rem", gap: "0.5rem" }}>
            <h3 style={{ margin: 0, marginBottom: "0.5rem" }}>💊 Drug Catalog</h3>
            <ProviderRow
              label="Active provider"
              value={status.drug_catalog ?? "none"}
            />
            <ProviderRow
              label="Data source"
              value={localLabel(status.drug_catalog)}
            />
          </section>

          <section className="card vstack" style={{ padding: "1rem", gap: "0.5rem" }}>
            <h3 style={{ margin: 0, marginBottom: "0.5rem" }}>🏥 Insurance / Adjudication</h3>
            <ProviderRow
              label="Active provider"
              value={status.insurance_gateway ?? "none"}
            />
            <ProviderRow
              label="Data source"
              value={localLabel(status.insurance_gateway)}
            />
          </section>

          <section className="card vstack" style={{ padding: "1rem", gap: "0.5rem" }}>
            <h3 style={{ margin: 0, marginBottom: "0.5rem" }}>ℹ️ About</h3>
            <p style={{ margin: 0, color: "var(--text-light)", fontSize: "0.9rem" }}>
              Providers are registered at backend startup via the{" "}
              <code>DRUG_CATALOG_PROVIDER</code> and{" "}
              <code>INSURANCE_GATEWAY_PROVIDER</code> environment variables.
              The default (<code>local</code>) reads from the PostgreSQL database.
              To seed production with local data, run:
            </p>
            <pre style={{ margin: 0, fontSize: "0.8rem", background: "rgba(0,0,0,0.2)", padding: "0.75rem", borderRadius: 4, overflowX: "auto" }}>
{`# 1. Export from local:
docker compose exec backend python seed_data.py export seed_data.json

# 2. Import on prod (ECS):
DATABASE_URL=<prod_url> python seed_data.py import seed_data.json`}
            </pre>
          </section>
        </div>
      )}
    </div>
  );
}

function ProviderRow({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: "flex", gap: "1rem", alignItems: "baseline" }}>
      <span style={{ color: "var(--text-light)", minWidth: 140, fontSize: "0.9rem" }}>{label}</span>
      <code style={{ fontSize: "0.9rem" }}>{value}</code>
    </div>
  );
}

function localLabel(providerClass: string | null): string {
  if (!providerClass) return "none";
  if (providerClass.toLowerCase().includes("local")) return "local PostgreSQL database";
  return "external / third-party";
}
