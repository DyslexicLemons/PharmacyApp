import { createContext, useContext, useState, useCallback, type ReactNode } from "react";
import type { Notification, NotificationType } from "@/types";

interface NotificationContextValue {
  notifications: Notification[];
  addNotification: (message: string, type?: NotificationType) => void;
  removeNotification: (id: number) => void;
}

const NotificationContext = createContext<NotificationContextValue | null>(null);

const FADE_START_MS = 18000; // start fading at 18s
const REMOVE_MS = 20000;     // remove at 20s
const DISMISS_FADE_MS = 600; // fade duration when manually dismissed

export function NotificationProvider({ children }: { children: ReactNode }) {
  const [notifications, setNotifications] = useState<Notification[]>([]);

  const addNotification = useCallback((message: string, type: NotificationType = "info") => {
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

  const removeNotification = useCallback((id: number) => {
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

export function useNotification(): NotificationContextValue {
  const ctx = useContext(NotificationContext);
  if (!ctx) throw new Error("useNotification must be used inside NotificationProvider");
  return ctx;
}
