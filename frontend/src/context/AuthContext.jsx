/**
 * AuthContext — thin bridge that keeps the same context API surface while
 * delegating all state to the Zustand authStore. Side-effects (DOM event
 * listeners, auth:expired handler) live here in the Provider component so
 * they are attached once at mount and cleaned up on unmount.
 *
 * Every existing component that does `useContext(AuthContext)` continues to
 * work unchanged. New code can also import `useAuthStore` directly from
 * @/stores/authStore for selector-based subscriptions.
 */
import { createContext, useEffect } from "react";
import { useAuthStore } from "@/stores/authStore";

export const AuthContext = createContext();

export function AuthProvider({ children }) {
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
