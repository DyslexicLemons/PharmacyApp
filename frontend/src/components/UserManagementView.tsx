import { useState, useContext, useEffect } from "react";
import { AuthContext } from "@/context/AuthContext";
import { getUsers, createUser } from "@/api";
import type { User } from "@/types";

interface UserManagementViewProps {
  onBack?: () => void;
}

export default function UserManagementView({ onBack }: UserManagementViewProps) {
  const { token } = useContext(AuthContext);

  const [users, setUsers] = useState<User[]>([]);
  const [loadError, setLoadError] = useState("");

  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newIsAdmin, setNewIsAdmin] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");
  const [createSuccess, setCreateSuccess] = useState("");

  useEffect(() => {
    if (!token) return;
    getUsers(token)
      .then(setUsers)
      .catch((err: Error) => setLoadError(err.message));
  }, [token]);

  async function handleCreate(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setCreateError("");
    setCreateSuccess("");
    setCreating(true);
    if (!token) { setCreateError("Not authenticated."); setCreating(false); return; }
    try {
      const created = await createUser(
        { username: newUsername, password: newPassword, is_admin: newIsAdmin },
        token
      );
      setUsers((prev) => [...prev, { id: created.id, username: created.username, is_admin: created.is_admin }]);
      setNewUsername("");
      setNewPassword("");
      setNewIsAdmin(false);
      setCreateSuccess(`User "${created.username}" created successfully.`);
    } catch (err) {
      setCreateError((err as Error).message);
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="vstack" style={{ maxWidth: 680, margin: "0 auto" }}>
      <div className="hstack" style={{ justifyContent: "space-between", alignItems: "center" }}>
        <h2 style={{ margin: 0 }}>User Management</h2>
        <button className="btn btn-secondary" onClick={onBack}>Back</button>
      </div>

      <div className="card vstack" style={{ gap: "0.75rem" }}>
        <h3 style={{ margin: 0, fontSize: "1rem" }}>Existing Users</h3>
        {loadError && <div style={{ color: "var(--danger)", fontSize: "0.85rem" }}>{loadError}</div>}
        <table className="table">
          <thead>
            <tr>
              <th>Username</th>
              <th>Role</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id}>
                <td>{u.username}</td>
                <td style={{ color: u.is_admin ? "var(--primary)" : "var(--text-light)" }}>
                  {u.is_admin ? "Admin" : "User"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card vstack" style={{ gap: "1rem" }}>
        <h3 style={{ margin: 0, fontSize: "1rem" }}>Create New User</h3>
        <form className="vstack" style={{ gap: "1rem" }} onSubmit={handleCreate}>
          <div className="hstack" style={{ gap: "0.75rem" }}>
            <div className="vstack" style={{ flex: 1, gap: "0.3rem" }}>
              <label style={{ fontSize: "0.85rem", fontWeight: 600, color: "var(--text-light)" }}>
                Username
              </label>
              <input
                className="input"
                type="text"
                value={newUsername}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setNewUsername(e.target.value)}
                required
              />
            </div>
            <div className="vstack" style={{ flex: 1, gap: "0.3rem" }}>
              <label style={{ fontSize: "0.85rem", fontWeight: 600, color: "var(--text-light)" }}>
                Password
              </label>
              <input
                className="input"
                type="password"
                value={newPassword}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setNewPassword(e.target.value)}
                required
              />
            </div>
          </div>
          <label className="hstack" style={{ gap: "0.5rem", alignItems: "center", cursor: "pointer", width: "fit-content" }}>
            <input
              type="checkbox"
              checked={newIsAdmin}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setNewIsAdmin(e.target.checked)}
              style={{ width: 16, height: 16 }}
            />
            <span style={{ fontSize: "0.9rem" }}>Grant admin privileges</span>
          </label>
          {createError && (
            <div style={{ color: "var(--danger)", fontSize: "0.85rem" }}>{createError}</div>
          )}
          {createSuccess && (
            <div style={{ color: "var(--success, #06d6a0)", fontSize: "0.85rem" }}>{createSuccess}</div>
          )}
          <button className="btn btn-primary" type="submit" disabled={creating} style={{ alignSelf: "flex-start" }}>
            {creating ? "Creating…" : "Create User"}
          </button>
        </form>
      </div>
    </div>
  );
}
