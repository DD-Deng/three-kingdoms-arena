import React from "react";
// ═══════════════════════════════════════════════════════════════
// dragon.jsx — Ink dragon emerging from the right cliff
// Uses dragon.png (ink-wash artwork, tinted) inside an SVG filter
// that animates feTurbulence for body undulation.
// State machine: idle → emerging → flying → fading → idle + cooldown
// ═══════════════════════════════════════════════════════════════

function InkDragon({ enabled = true }) {
  const [phase, setPhase] = React.useState("idle");
  const [reduced, setReduced] = React.useState(false);
  const cooldownRef = React.useRef(false);

  React.useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const u = () => setReduced(mq.matches || window.innerWidth < 720);
    u();
    mq.addEventListener?.("change", u);
    window.addEventListener("resize", u);
    return () => {
      mq.removeEventListener?.("change", u);
      window.removeEventListener("resize", u);
    };
  }, []);

  React.useEffect(() => {
    if (!enabled || reduced) return;
    const onMove = (e) => {
      if (cooldownRef.current) return;
      // Only trigger near the top of the page (hero region)
      if (window.scrollY > 120) return;
      const nx = e.clientX / window.innerWidth;
      const ny = e.clientY / window.innerHeight;
      // Right cliff zone (user-circled region in viewport)
      if (nx >= 0.58 && nx <= 0.96 && ny >= 0.06 && ny <= 0.52) {
        cooldownRef.current = true;
        setPhase("emerging");
        setTimeout(() => setPhase("fading"), 2200);
        setTimeout(() => {
          setPhase("idle");
          setTimeout(() => { cooldownRef.current = false; }, 800);
        }, 5400);
      }
    };
    document.addEventListener("mousemove", onMove, { passive: true });
    return () => document.removeEventListener("mousemove", onMove);
  }, [enabled, reduced]);

  if (!enabled || reduced) return null;

  return (
    <div className={`ink-dragon-wrap phase-${phase}`} aria-hidden="true">
      <svg className="ink-dragon" viewBox="0 0 786 999"
           preserveAspectRatio="xMidYMid meet">
        <defs>
          {/* Animated turbulence creates a continuously undulating body */}
          <filter id="ink-undulate" x="-20%" y="-20%" width="140%" height="140%">
            <feTurbulence type="fractalNoise"
                          baseFrequency="0.012 0.020"
                          numOctaves="2" seed="3">
              <animate attributeName="baseFrequency"
                       values="0.010 0.018;0.015 0.022;0.010 0.018;0.012 0.020;0.010 0.018"
                       dur="7s" repeatCount="indefinite" />
              <animate attributeName="seed"
                       values="3;7;11;3"
                       dur="9s" repeatCount="indefinite" />
            </feTurbulence>
            <feDisplacementMap in="SourceGraphic" scale="16" />
          </filter>
        </defs>
        <image href="/images/dragon.png" width="786" height="999"
               filter="url(#ink-undulate)" />
      </svg>
    </div>
  );
}

export { InkDragon };
