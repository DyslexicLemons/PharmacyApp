import { useNotification } from "@/context/NotificationContext";
import type { NotificationType } from "@/types";

interface TypeStyle {
  background: string;
  border: string;
  iconColor: string;
  icon: string;
}

const TYPE_STYLES: Record<NotificationType, TypeStyle> = {
  success: {
    background: "rgba(6, 214, 160, 0.15)",
    border: "1px solid var(--success, #06d6a0)",
    iconColor: "var(--success, #06d6a0)",
    icon: "✓",
  },
  error: {
    background: "rgba(239, 71, 111, 0.15)",
    border: "1px solid var(--danger, #ef476f)",
    iconColor: "var(--danger, #ef476f)",
    icon: "✕",
  },
  warning: {
    background: "rgba(255, 190, 11, 0.15)",
    border: "1px solid #ffbe0b",
    iconColor: "#ffbe0b",
    icon: "⚠",
  },
  info: {
    background: "rgba(76, 201, 240, 0.15)",
    border: "1px solid var(--primary, #4cc9f0)",
    iconColor: "var(--primary, #4cc9f0)",
    icon: "ℹ",
  },
};

export default function NotificationPanel() {
  const { notifications, removeNotification } = useNotification();

  if (notifications.length === 0) return null;

  return (
    <div
      style={{
        position: "fixed",
        left: "16px",
        top: "50%",
        transform: "translateY(-50%)",
        zIndex: 5000,
        display: "flex",
        flexDirection: "column",
        gap: "8px",
        width: "300px",
        pointerEvents: "none",
      }}
    >
      {notifications.map((n) => {
        const s = TYPE_STYLES[n.type] ?? TYPE_STYLES.info;
        return (
          <div
            key={n.id}
            style={{
              background: s.background,
              border: s.border,
              borderRadius: "8px",
              padding: "12px 14px",
              display: "flex",
              alignItems: "flex-start",
              gap: "10px",
              boxShadow: "0 4px 16px rgba(0,0,0,0.35)",
              opacity: n.fading ? 0 : 1,
              transition: "opacity 0.6s ease",
              pointerEvents: "all",
            }}
          >
            <span
              style={{
                color: s.iconColor,
                fontWeight: "bold",
                fontSize: "1rem",
                lineHeight: 1.4,
                flexShrink: 0,
              }}
            >
              {s.icon}
            </span>
            <span
              style={{
                flex: 1,
                fontSize: "0.9rem",
                color: "#ffffff",
                lineHeight: 1.5,
                whiteSpace: "pre-line",
              }}
            >
              {n.message}
            </span>
            <button
              onClick={() => removeNotification(n.id)}
              style={{
                background: "none",
                border: "none",
                cursor: "pointer",
                color: "var(--text-light, #888)",
                fontSize: "0.85rem",
                lineHeight: 1,
                padding: "2px",
                flexShrink: 0,
              }}
              title="Dismiss"
            >
              ✕
            </button>
          </div>
        );
      })}
    </div>
  );
}
