"use client";

interface Props {
  probability: number;
  size?: number;
  color?: string;
}

export default function ProbabilityArc({ probability, size = 80, color }: Props) {
  const p   = Math.max(0, Math.min(1, probability));
  const c   = color ?? (p >= 0.6 ? "#4ade80" : p >= 0.35 ? "#fbbf24" : "#f87171");
  const r   = (size - 10) / 2;
  const cx  = size / 2;
  const arc = Math.PI * r;
  const dash = arc * p;
  const gap  = arc - dash;

  return (
    <div style={{ position: "relative", width: size, height: size / 2 + 10, overflow: "visible" }}>
      <svg width={size} height={size} style={{ position: "absolute", top: 0, overflow: "visible" }}>
        {/* Track */}
        <path
          d={`M 5 ${cx} A ${r} ${r} 0 0 1 ${size - 5} ${cx}`}
          fill="none" stroke="#1e1e1e" strokeWidth="5" strokeLinecap="round"
        />
        {/* Fill */}
        <path
          d={`M 5 ${cx} A ${r} ${r} 0 0 1 ${size - 5} ${cx}`}
          fill="none" stroke={c} strokeWidth="5" strokeLinecap="round"
          strokeDasharray={`${dash} ${gap + 0.01}`}
          style={{
            filter: `drop-shadow(0 0 8px ${c}88)`,
            transition: "stroke-dasharray 1s cubic-bezier(0.16,1,0.3,1)",
          }}
        />
      </svg>
      <div style={{
        position: "absolute", bottom: 0, left: "50%", transform: "translateX(-50%)",
        fontFamily: "var(--font-mono), monospace", fontSize: size < 70 ? "13px" : "16px",
        fontWeight: 700, color: c, whiteSpace: "nowrap",
        textShadow: `0 0 16px ${c}66`,
      }}>
        {(p * 100).toFixed(1)}%
      </div>
    </div>
  );
}
