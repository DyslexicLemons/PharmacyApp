import { createContext, useContext, useState, useCallback } from "react";

const NotificationContext = createContext(null);

const FADE_START_MS = 18000; // start fading at 18s
const REMOVE_MS = 20000;     // remove at 20s
const DISMISS_FADE_MS = 300; // fade duration when manually dismissed

export function NotificationProvider({ children }) {
  const [notifications, setNotifications] = useState([]);

  const addNotification = useCallback((message, type = "info") => {
    const id = Date.now() + Math.random();
    setNotifications((prev) => [...prev, { id, message, type, fading: false }]);

    setTimeout(() => {
      setNotifications((prev) =>
        prev.map((n) => (n.id === id ? { ...n, fading: true } : n))
      );
    }, FADE_START_MS);

    setTimeout(() => {
      setNotifications((prev) => prev.filter((n) => n.id !== id));
    }, REMOVE_MS);
  }, []);

  const removeNotification = useCallback((id) => {
    setNotifications((prev) =>
      prev.map((n) => (n.id === id ? { ...n, fading: true } : n))
    );
    setTimeout(() => {
      setNotifications((prev) => prev.filter((n) => n.id !== id));
    }, DISMISS_FADE_MS);
  }, []);

  return (
    <NotificationContext.Provider value={{ notifications, addNotification, removeNotification }}>
      {children}
    </NotificationContext.Provider>
  );
}

export function useNotification() {
  return useContext(NotificationContext);
}
