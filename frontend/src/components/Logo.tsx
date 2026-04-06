interface LogoProps {
  size?: number;
  showTagline?: boolean;
}

export default function Logo({ size = 80, showTagline = true }: LogoProps) {
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
      <svg
        width={size}
        height={size}
        viewBox="0 0 200 200"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        aria-label="joeMed logo"
      >
        {/* Blue orbital ring */}
        <ellipse
          cx="100"
          cy="100"
          rx="88"
          ry="36"
          stroke="#1d5fa6"
          strokeWidth="5"
          fill="none"
        />

        {/* Green orbital ring – rotated 60° */}
        <ellipse
          cx="100"
          cy="100"
          rx="88"
          ry="36"
          stroke="#3a9e52"
          strokeWidth="5"
          fill="none"
          transform="rotate(60 100 100)"
        />

        {/* Green orbital ring – rotated 120° */}
        <ellipse
          cx="100"
          cy="100"
          rx="88"
          ry="36"
          stroke="#3a9e52"
          strokeWidth="5"
          fill="none"
          transform="rotate(120 100 100)"
        />

        {/* Orbital dots – dark navy */}
        <circle cx="188" cy="100" r="7" fill="#1a2e5e" />
        <circle cx="12"  cy="100" r="7" fill="#1a2e5e" />
        <circle cx="56"  cy="31"  r="7" fill="#1a2e5e" />
        <circle cx="144" cy="169" r="7" fill="#1a2e5e" />

        {/* Capsule body – blue half */}
        <path
          d="M100 74 C88 74 78 84 78 100 C78 116 88 126 100 126 L100 74 Z"
          fill="#1d5fa6"
        />
        {/* Capsule body – green half */}
        <path
          d="M100 74 C112 74 122 84 122 100 C122 116 112 126 100 126 L100 74 Z"
          fill="#3a9e52"
        />
        {/* Capsule divider line */}
        <line x1="100" y1="74" x2="100" y2="126" stroke="white" strokeWidth="2.5" />
        {/* Capsule outline */}
        <rect x="78" y="74" width="44" height="52" rx="22" fill="none" stroke="white" strokeWidth="1.5" />
      </svg>

      {/* Wordmark */}
      <div style={{ lineHeight: 1, textAlign: "center" }}>
        <span
          style={{
            fontFamily: "'Inter', 'Segoe UI', system-ui, Arial, sans-serif",
            fontWeight: 700,
            fontSize: size * 0.3,
            color: "#1a2e5e",
            letterSpacing: "-0.01em",
          }}
        >
          joe
        </span>
        <span
          style={{
            fontFamily: "'Inter', 'Segoe UI', system-ui, Arial, sans-serif",
            fontWeight: 700,
            fontSize: size * 0.3,
            color: "#3a9e52",
            letterSpacing: "-0.01em",
          }}
        >
          Med
        </span>
      </div>

      {showTagline && (
        <div
          style={{
            fontFamily: "'Inter', 'Segoe UI', system-ui, Arial, sans-serif",
            fontWeight: 500,
            fontSize: size * 0.1,
            letterSpacing: "0.18em",
            color: "#4a5568",
            textTransform: "uppercase" as const,
          }}
        >
          Pharmaceutical Innovation
        </div>
      )}
    </div>
  );
}
