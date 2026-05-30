// ═══════════════════════════════════════════════════════════════
// ink-landscape.jsx — 马远《踏歌图》笔触作背景(已抠去绢底)
// 三种布局: scroll(中轴) / mirror(镜像) / fill(满幅,4 联横幅复合图)
// ═══════════════════════════════════════════════════════════════

const PAINTING = "/images/landscape-strokes.png";
const PAINTING_WIDE = "/images/landscape-wide.png";
const P_W = 729, P_H = 1280;

const Z_CLIFF   = { x: 40,  y: 170, w: 280, h: 620 };
const Z_BAMBOO  = { x: 540, y: 780, w: 200, h: 380 };
const Z_DANCERS = { x: 380, y: 1080, w: 290, h: 160 };

function ptIn(z, x, y) {
  return x >= z.x && x <= z.x + z.w && y >= z.y && y <= z.y + z.h;
}

function InkLandscape({ opacity = 0.45, motion = true, layout = "mirror" }) {
  const rootRef = React.useRef(null);
  const [zone, setZone] = React.useState(null);
  const [reducedMotion, setReducedMotion] = React.useState(false);

  React.useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReducedMotion(mq.matches || window.innerWidth < 720);
    update();
    mq.addEventListener?.("change", update);
    window.addEventListener("resize", update);
    return () => {
      mq.removeEventListener?.("change", update);
      window.removeEventListener("resize", update);
    };
  }, []);

  React.useEffect(() => {
    if (reducedMotion || !motion) return;
    if (layout === "fill") return;
    const el = rootRef.current; if (!el) return;
    let raf = null, last = null;
    const tick = () => {
      raf = null;
      if (!last) return;
      const img = el.querySelector(".il-main");
      if (!img) return;
      const r = img.getBoundingClientRect();
      if (last.clientX < r.left || last.clientX > r.right ||
          last.clientY < r.top  || last.clientY > r.bottom) {
        setZone(null); return;
      }
      const sx = (last.clientX - r.left) / r.width  * P_W;
      const sy = (last.clientY - r.top)  / r.height * P_H;
      let z = null;
      if (ptIn(Z_CLIFF, sx, sy))         z = "cliff";
      else if (ptIn(Z_BAMBOO, sx, sy))   z = "bamboo";
      else if (ptIn(Z_DANCERS, sx, sy))  z = "dancers";
      setZone(z);
    };
    const onMove = (e) => { last = e; if (raf == null) raf = requestAnimationFrame(tick); };
    document.addEventListener("mousemove", onMove, { passive: true });
    return () => {
      document.removeEventListener("mousemove", onMove);
      if (raf != null) cancelAnimationFrame(raf);
    };
  }, [reducedMotion, motion, layout]);

  const cls = ["ink-landscape", `lay-${layout}`];
  cls.push(reducedMotion || !motion ? "still" : "alive");
  if (zone) cls.push(`hover-${zone}`);

  return (
    <div ref={rootRef} className={cls.join(" ")} style={{ opacity }}>
      <img className="il-main" src={PAINTING}
           alt="" aria-hidden="true" />
      {layout === "mirror" && (
        <>
          <img className="il-mirror il-left"  src={PAINTING} alt="" aria-hidden="true" />
          <img className="il-mirror il-right" src={PAINTING} alt="" aria-hidden="true" />
        </>
      )}

      <svg className="il-overlay" viewBox={`0 0 ${P_W} ${P_H}`}
           preserveAspectRatio="xMidYMid meet" aria-hidden="true">
        <defs>
          <linearGradient id="il-mist-band2" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%"   stopColor="#f3ead7" stopOpacity="0" />
            <stop offset="35%"  stopColor="#f3ead7" stopOpacity="0.85" />
            <stop offset="65%"  stopColor="#f3ead7" stopOpacity="0.85" />
            <stop offset="100%" stopColor="#f3ead7" stopOpacity="0" />
          </linearGradient>
          <radialGradient id="il-glow-cliff2" cx="0.5" cy="0.5" r="0.5">
            <stop offset="0%"   stopColor="#1f1a16" stopOpacity="0.22" />
            <stop offset="100%" stopColor="#1f1a16" stopOpacity="0" />
          </radialGradient>
          <radialGradient id="il-puff2" cx="0.5" cy="0.5" r="0.5">
            <stop offset="0%"   stopColor="#f3ead7" stopOpacity="0.7" />
            <stop offset="100%" stopColor="#f3ead7" stopOpacity="0" />
          </radialGradient>
        </defs>

        <ellipse className="il-cliff-glow" cx="180" cy="450" rx="180" ry="320"
                 fill="url(#il-glow-cliff2)" />

        <g className="il-mist-wrap">
          <rect x="-200" y="700"  width="1200" height="220" fill="url(#il-mist-band2)" opacity="0.6" />
          <rect x="-200" y="900"  width="1200" height="180" fill="url(#il-mist-band2)" opacity="0.45" />
        </g>

        <g className="il-puff">
          <ellipse cx="200" cy="780" rx="200" ry="28" fill="url(#il-puff2)" />
          <ellipse cx="240" cy="800" rx="160" ry="22" fill="url(#il-puff2)" />
        </g>

        <g className="il-bamboo">
          <g stroke="#1f1a16" strokeWidth="0.7" fill="none" opacity="0.55">
            <path d="M 620 880 q -8 -4 -16 -2" />
            <path d="M 620 880 q -10 4 -16 6" />
            <path d="M 640 920 q -6 -6 -14 -4" />
            <path d="M 640 920 q -8 4 -14 8" />
            <path d="M 670 960 q 4 -6 12 -4" />
            <path d="M 670 960 q 6 4 12 6" />
            <path d="M 600 1000 q -8 -6 -16 -2" />
            <path d="M 600 1000 q -4 8 -10 12" />
          </g>
        </g>

        <g className="il-puff-dancers">
          <ellipse cx="445" cy="1180" rx="16" ry="3.5" fill="url(#il-puff2)" />
          <ellipse cx="500" cy="1200" rx="18" ry="3.5" fill="url(#il-puff2)" />
          <ellipse cx="560" cy="1190" rx="16" ry="3.5" fill="url(#il-puff2)" />
          <ellipse cx="620" cy="1205" rx="14" ry="3.5" fill="url(#il-puff2)" />
        </g>
      </svg>
    </div>
  );
}

export { InkLandscape };
