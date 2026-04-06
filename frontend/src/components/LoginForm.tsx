import React, { useState, useContext, useEffect, useRef } from "react";
import { AuthContext } from "@/context/AuthContext";
import Logo from "@/components/Logo";

interface LoginFormProps {
  isModal?: boolean;
}

interface ErrorBoxProps {
  message: string;
}

function ErrorBox({ message }: ErrorBoxProps) {
  return (
    <div
      style={{
        background: "rgba(239, 71, 111, 0.1)",
        border: "1px solid var(--danger)",
        borderRadius: 8,
        padding: "8px 12px",
        fontSize: "0.85rem",
        color: "var(--danger)",
      }}
    >
      {message}
    </div>
  );
}

export default function LoginForm({ isModal = false }: LoginFormProps) {
  const { login, loginByCode, timedOut, quickCode, clearQuickCode } = useContext(AuthContext);
  const [tab, setTab] = useState("code"); // "credentials" | "code"
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [codeInput, setCodeInput] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const usernameRef = useRef<HTMLInputElement>(null);
  const codeRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (tab === "credentials") usernameRef.current?.focus();
    else codeRef.current?.focus();
  }, [tab]);

  async function handleCredentialsSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(username, password);
    } catch {
      setError("Invalid username or password.");
      setPassword("");
    } finally {
      setLoading(false);
    }
  }

  async function handleCodeSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await loginByCode(codeInput);
    } catch (err) {
      setError((err as Error).message || "Invalid or expired code.");
      setCodeInput("");
    } finally {
      setLoading(false);
    }
  }

  // Remaining seconds for the quick code
  const [remaining, setRemaining] = useState<number | null>(null);
  useEffect(() => {
    if (!quickCode) { setRemaining(null); return; }
    function tick() {
      const secs = Math.max(0, Math.round((quickCode!.expiresAt - Date.now()) / 1000));
      setRemaining(secs);
      if (secs === 0) clearQuickCode();
    }
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [quickCode, clearQuickCode]);

  const card = (
    <div
      className="card"
      style={{ width: 360, padding: "40px 36px", display: "flex", flexDirection: "column", gap: "24px" }}
    >
      <div style={{ textAlign: "center" }}>
        <Logo size={100} showTagline={false} />
        <div style={{ fontSize: "0.85rem", color: "var(--text-light)", marginTop: 8 }}>
          Pharmacy Management System
        </div>
      </div>

      {timedOut && (
        <div
          style={{
            background: "rgba(255, 209, 102, 0.15)",
            border: "1px solid var(--warning)",
            borderRadius: 8,
            padding: "10px 14px",
            fontSize: "0.85rem",
            color: "#856404",
            textAlign: "center",
          }}
        >
          Session timed out due to inactivity. Please log in again.
        </div>
      )}

      {/* Quick code display (shown when a code is active after login in same session) */}
      {quickCode && remaining != null && remaining > 0 && (
        <div
          style={{
            background: "rgba(6, 214, 160, 0.1)",
            border: "1px solid var(--success, #06d6a0)",
            borderRadius: 8,
            padding: "12px 14px",
            textAlign: "center",
          }}
        >
          <div style={{ fontSize: "0.75rem", color: "var(--text-light)", marginBottom: 4 }}>
            Your quick login code
          </div>
          <div style={{ fontSize: "2rem", fontWeight: 800, letterSpacing: "0.25em", color: "var(--primary)", fontFamily: "monospace" }}>
            {quickCode.code}
          </div>
          <div style={{ fontSize: "0.75rem", color: "var(--text-light)", marginTop: 4 }}>
            expires in {Math.floor(remaining / 60)}:{String(remaining % 60).padStart(2, "0")}
          </div>
        </div>
      )}

      {/* Tab switcher */}
      <div style={{ display: "flex", borderBottom: "1px solid var(--border)", gap: 0 }}>
        {([["code", "Quick Code"], ["credentials", "Sign In"]] as [string, string][]).map(([key, label]) => (
          <button
            key={key}
            type="button"
            onClick={() => { setTab(key); setError(""); }}
            style={{
              flex: 1,
              background: "none",
              border: "none",
              borderBottom: tab === key ? "2px solid var(--primary)" : "2px solid transparent",
              color: tab === key ? "var(--primary)" : "var(--text-light)",
              fontWeight: tab === key ? 700 : 400,
              fontSize: "0.85rem",
              padding: "8px 0",
              cursor: "pointer",
              marginBottom: -1,
            }}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "credentials" ? (
        <form onSubmit={handleCredentialsSubmit} style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <label style={{ fontSize: "0.85rem", fontWeight: 600, color: "var(--text-light)" }}>
              Username
            </label>
            <input
              ref={usernameRef}
              className="input"
              type="text"
              value={username}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setUsername(e.target.value)}
              autoComplete="username"
              required
            />
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <label style={{ fontSize: "0.85rem", fontWeight: 600, color: "var(--text-light)" }}>
              Password
            </label>
            <input
              className="input"
              type="password"
              value={password}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
          </div>

          {error && <ErrorBox message={error} />}

          <button className="btn btn-primary" type="submit" disabled={loading} style={{ marginTop: 4 }}>
            {loading ? "Signing in…" : "Sign In"}
          </button>
        </form>
      ) : (
        <form onSubmit={handleCodeSubmit} style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <label style={{ fontSize: "0.85rem", fontWeight: 600, color: "var(--text-light)" }}>
              3-Character Code
            </label>
            <input
              ref={codeRef}
              className="input"
              type="text"
              value={codeInput}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setCodeInput(e.target.value.replace(/[^a-zA-Z]/g, "").toUpperCase().slice(0, 3))}
              placeholder="ABC"
              maxLength={3}
              autoComplete="off"
              required
              style={{ textAlign: "center", fontSize: "1.5rem", fontWeight: 700, letterSpacing: "0.3em", fontFamily: "monospace" }}
            />
            <div style={{ fontSize: "0.78rem", color: "var(--text-light)", textAlign: "center" }}>
              Use the code shown after your last sign-in (valid 10 min)
            </div>
          </div>

          {error && <ErrorBox message={error} />}

          <button
            className="btn btn-primary"
            type="submit"
            disabled={loading || codeInput.length !== 3}
            style={{ marginTop: 4 }}
          >
            {loading ? "Verifying…" : "Sign In with Code"}
          </button>
        </form>
      )}
    </div>
  );

  if (isModal) return card;

  return (
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center" }}>
      {card}
    </div>
  );
}
