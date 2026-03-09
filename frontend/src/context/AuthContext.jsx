import { createContext, useState, useEffect, useCallback, useRef } from "react";
import { loginUser, loginWithCode } from "@/api";

export const AuthContext = createContext();

const TIMEOUT_MS = 5 * 60 * 1000;        // 5 minutes of inactivity → session timeout
const IDLE_RESET_MS = 30 * 60 * 1000;    // 30 minutes logged-out → reset to home
const QUICK_CODE_TTL_MS = 10 * 60 * 1000; // quick code expires in 10 minutes

export function AuthProvider({ children }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [timedOut, setTimedOut] = useState(false);
  const [shouldResetToHome, setShouldResetToHome] = useState(false);
  const [authUser, setAuthUser] = useState(null); // { username, isAdmin }
  const [quickCode, setQuickCode] = useState(null); // { code, expiresAt }
  const [token, setToken] = useState(null); // JWT access token (in-memory only)
  const timerRef = useRef(null);
  const idleResetTimerRef = useRef(null);
  const quickCodeTimerRef = useRef(null);

  const clearQuickCode = useCallback(() => {
    setQuickCode(null);
    if (quickCodeTimerRef.current) clearTimeout(quickCodeTimerRef.current);
  }, []);

  const setQuickCodeWithExpiry = useCallback((code) => {
    if (quickCodeTimerRef.current) clearTimeout(quickCodeTimerRef.current);
    const expiresAt = Date.now() + QUICK_CODE_TTL_MS;
    setQuickCode({ code, expiresAt });
    quickCodeTimerRef.current = setTimeout(() => setQuickCode(null), QUICK_CODE_TTL_MS);
  }, []);

  const logout = useCallback(() => {
    setIsAuthenticated(false);
    setAuthUser(null);
    setToken(null);
    setTimedOut(true);
    clearQuickCode();
    if (timerRef.current) clearTimeout(timerRef.current);
    // Start 30-min idle timer: if still logged out, signal home reset
    if (idleResetTimerRef.current) clearTimeout(idleResetTimerRef.current);
    idleResetTimerRef.current = setTimeout(() => setShouldResetToHome(true), IDLE_RESET_MS);
  }, [clearQuickCode]);

  const resetTimer = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(logout, TIMEOUT_MS);
  }, [logout]);

  const _applyLoginData = useCallback((data) => {
    setIsAuthenticated(true);
    setAuthUser({ username: data.username, isAdmin: data.is_admin });
    setToken(data.access_token ?? null);
    setTimedOut(false);
    setShouldResetToHome(false);
    if (idleResetTimerRef.current) clearTimeout(idleResetTimerRef.current);
    if (data.quick_code) setQuickCodeWithExpiry(data.quick_code);
    resetTimer();
  }, [resetTimer, setQuickCodeWithExpiry]);

  const login = useCallback(async (username, password) => {
    const data = await loginUser(username, password); // throws on bad credentials
    _applyLoginData(data);
  }, [_applyLoginData]);

  const loginByCode = useCallback(async (code) => {
    const data = await loginWithCode(code); // throws on bad/expired code
    _applyLoginData(data);
  }, [_applyLoginData]);

  const clearHomeReset = useCallback(() => setShouldResetToHome(false), []);

  // Auto-logout when the API returns 401 (token expired server-side)
  useEffect(() => {
    const handler = () => logout();
    window.addEventListener("auth:expired", handler);
    return () => window.removeEventListener("auth:expired", handler);
  }, [logout]);

  // Attach activity listeners only while authenticated
  useEffect(() => {
    if (!isAuthenticated) return;

    const events = ["mousemove", "mousedown", "keydown", "touchstart", "scroll"];
    events.forEach((e) => window.addEventListener(e, resetTimer, { passive: true }));

    return () => {
      events.forEach((e) => window.removeEventListener(e, resetTimer));
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [isAuthenticated, resetTimer]);

  return (
    <AuthContext.Provider value={{ isAuthenticated, timedOut, shouldResetToHome, clearHomeReset, login, loginByCode, logout, authUser, quickCode, clearQuickCode, token }}>
      {children}
    </AuthContext.Provider>
  );
}
