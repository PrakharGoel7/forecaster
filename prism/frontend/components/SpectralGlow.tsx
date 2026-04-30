"use client";

export default function SpectralGlow() {
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden">
      {/* Warm orange bloom — primary prism beam */}
      <div style={{
        position: "absolute",
        width: "700px", height: "500px",
        left: "50%", top: "45%",
        transform: "translate(-50%, -50%)",
        background: "radial-gradient(ellipse at center, rgba(227,100,56,0.1) 0%, transparent 65%)",
        filter: "blur(48px)",
        animation: "glow-breathe 7s ease-in-out infinite",
      }} />
      {/* Blue bloom — refracted beam, offset right */}
      <div style={{
        position: "absolute",
        width: "560px", height: "380px",
        left: "62%", top: "52%",
        transform: "translate(-50%, -50%)",
        background: "radial-gradient(ellipse at center, rgba(91,156,246,0.07) 0%, transparent 65%)",
        filter: "blur(56px)",
        animation: "glow-breathe-alt 9s ease-in-out infinite",
        animationDelay: "3.5s",
      }} />
      {/* Spectrum strip — light split across the scene */}
      <div style={{
        position: "absolute",
        left: "50%", top: "56%",
        width: "800px", height: "3px",
        background: "linear-gradient(90deg, transparent 0%, rgba(91,156,246,0.25) 25%, rgba(168,85,247,0.15) 45%, rgba(227,100,56,0.25) 70%, transparent 100%)",
        filter: "blur(4px)",
        opacity: 0.5,
        animation: "spectrum-drift 12s ease-in-out infinite",
      }} />
    </div>
  );
}
