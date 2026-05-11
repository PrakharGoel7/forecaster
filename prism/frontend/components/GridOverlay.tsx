"use client";

export default function GridOverlay() {
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden">
      <svg
        width="100%" height="100%"
        style={{ position: "absolute", inset: 0, opacity: 0.06 }}
        xmlns="http://www.w3.org/2000/svg"
      >
        <defs>
          <pattern id="prism-grid" width="52" height="52" patternUnits="userSpaceOnUse">
            <path d="M 52 0 L 0 0 0 52" fill="none" stroke="#1c1814" strokeWidth="0.5" />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#prism-grid)" />
      </svg>
      <div style={{
        position: "absolute", inset: 0,
        background: "radial-gradient(ellipse 75% 65% at 50% 50%, transparent 20%, #f8f6f2 100%)",
      }} />
    </div>
  );
}
