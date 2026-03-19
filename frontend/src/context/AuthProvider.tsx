import { useEffect, type ReactNode } from "react";
import { useAuthStore } from "@/stores/authStore";
import { AuthContext } from "./AuthContext";

export function AuthProvider({ children }: { children: ReactNode }) {
  const store = useAuthStore();
  const { isAuthenticated, resetTimer, logout } = store;

  // Auto-logout when the API returns 401 (token expired server-side)
  useEffect(() => {
    const handler = () => logout();
    window.addEventListener("auth:expired", handler);
    return () => window.removeEventListener("auth:expired", handler);
  }, [logout]);

  // Attach activity listeners only while authenticated.
  // resetTimer only touches module-level timers (no Zustand set), so this
  // effect does not trigger re-renders on user activity.
  useEffect(() => {
    if (!isAuthenticated) return;
    const events = ["mousemove", "mousedown", "keydown", "touchstart", "scroll"];
    events.forEach((e) => window.addEventListener(e, resetTimer, { passive: true }));
    return () => {
      events.forEach((e) => window.removeEventListener(e, resetTimer));
    };
  }, [isAuthenticated, resetTimer]);

  return (
    <AuthContext.Provider value={store}>
      {children}
    </AuthContext.Provider>
  );
}
