import React from "react";
// ═══════════════════════════════════════════════════════════════
// hero-battle.jsx — Animated map for the homepage hero scroll
// Modes:
//   "auto"   — try live → replay → demo  (production default)
//   "live"   — poll /v1/lobby/status, display real cities
//   "replay" — fetch /api/battles/latest, step through ticks
//   "demo"   — synthetic battle simulation (no backend needed)
// ═══════════════════════════════════════════════════════════════

const HB_CITIES = [
  { id: "长安", en: "Chang'an",  faction: "蜀", x: 0.18, y: 0.30 },
  { id: "洛阳", en: "Luoyang",   faction: "魏", x: 0.50, y: 0.22 },
  { id: "邺城", en: "Yecheng",   faction: "魏", x: 0.82, y: 0.20 },
  { id: "宛城", en: "Wancheng",  faction: null, x: 0.42, y: 0.50 },
  { id: "襄阳", en: "Xiangyang", faction: null, x: 0.62, y: 0.66 },
  { id: "成都", en: "Chengdu",   faction: "蜀", x: 0.16, y: 0.74 },
  { id: "建业", en: "Jianye",    faction: "吴", x: 0.84, y: 0.62 },
];

const HB_FACTIONS = {
  蜀: { color: "var(--shu)", leader: "刘备", glyph: "蜀" },
  魏: { color: "var(--wei)", leader: "曹操", glyph: "魏" },
  吴: { color: "var(--wu)",  leader: "孙权", glyph: "吴" },
};
const HB_FACTION_HEX = { 蜀: "#b03a2e", 魏: "#2d4f78", 吴: "#2d6b3d" };

const HB_ADJ = {
  "长安": ["洛阳", "成都", "宛城"],
  "洛阳": ["长安", "宛城", "邺城"],
  "邺城": ["洛阳", "宛城"],
  "宛城": ["长安", "洛阳", "邺城", "襄阳"],
  "襄阳": ["宛城", "成都", "建业"],
  "成都": ["长安", "襄阳"],
  "建业": ["襄阳"],
};

// ── Demo engine ──────────────────────────────────────────────
function HB_initSynth() {
  const s = {};
  HB_CITIES.forEach((c) => {
    s[c.id] = {
      owner: c.faction,
      troops: c.faction ? 950 + Math.floor(Math.random() * 200) : 550 + Math.floor(Math.random() * 200),
      flash: 0,
    };
  });
  return s;
}
function HB_pickAttack(state) {
  const owned = HB_CITIES.filter((c) => state[c.id].owner).sort(() => Math.random() - 0.5);
  for (const src of owned) {
    if (state[src.id].troops < 240) continue;
    const adj = HB_ADJ[src.id] || [];
    const targets = adj
      .map((n) => HB_CITIES.find((c) => c.id === n))
      .filter((c) => c && state[c.id].owner !== state[src.id].owner);
    if (!targets.length) continue;
    const tgt = targets[Math.floor(Math.random() * targets.length)];
    return {
      src: src.id, tgt: tgt.id,
      atkFaction: state[src.id].owner,
      defFaction: state[tgt.id].owner,
      troops: Math.floor(state[src.id].troops * (0.4 + Math.random() * 0.3)),
    };
  }
  return null;
}
function HB_pickDiplo() {
  if (Math.random() > 0.32) return null;
  const fac = ["蜀", "魏", "吴"];
  const a = fac[Math.floor(Math.random() * 3)];
  let b = fac[Math.floor(Math.random() * 3)]; while (b === a) b = fac[Math.floor(Math.random() * 3)];
  const kinds = [
    `${a} → ${b}:遣使求盟`,
    `${b} → ${a}:歃血为盟`,
    `${a} 宣战 ${b}`,
    `${a} 单方面撕毁与 ${b} 之盟`,
  ];
  return { text: kinds[Math.floor(Math.random() * kinds.length)], kind: "diplo", faction: a };
}

// ── Mock replay (used in preview when /api/battles/latest is unreachable) ──
const HB_MOCK_REPLAY = {
  battle_id: 181, model: "claude-sonnet-4.5", winner: "蜀", total_ticks: 23,
  ticks: [
    { tick: 3,  cities: { 长安:{o:"蜀",t:980}, 洛阳:{o:"魏",t:1080}, 邺城:{o:"魏",t:1080}, 宛城:{o:null,t:600}, 襄阳:{o:null,t:600}, 成都:{o:"蜀",t:1080}, 建业:{o:"吴",t:1080} },
      events: [{ kind:"diplo", faction:"蜀", text:"蜀 → 吴:遣使求盟" }] },
    { tick: 5,  cities: { 长安:{o:"蜀",t:600}, 洛阳:{o:"魏",t:1100}, 邺城:{o:"魏",t:1100}, 宛城:{o:"蜀",t:380}, 襄阳:{o:null,t:620}, 成都:{o:"蜀",t:1100}, 建业:{o:"吴",t:1140} },
      events: [{ kind:"battle", faction:"蜀", text:"蜀 自长安出兵 400,攻陷 宛城" },
               { kind:"diplo",  faction:"吴", text:"吴 → 蜀:歃血为盟" }] },
    { tick: 7,  cities: { 长安:{o:"蜀",t:660}, 洛阳:{o:"魏",t:780}, 邺城:{o:"魏",t:1100}, 宛城:{o:"蜀",t:460}, 襄阳:{o:"吴",t:420}, 成都:{o:"蜀",t:1180}, 建业:{o:"吴",t:880} },
      events: [{ kind:"battle", faction:"吴", text:"吴 自建业出兵 320,攻陷 襄阳" },
               { kind:"diplo",  faction:"魏", text:"魏 宣战 蜀" }] },
    { tick: 9,  cities: { 长安:{o:"魏",t:700}, 洛阳:{o:"魏",t:540}, 邺城:{o:"魏",t:1120}, 宛城:{o:"蜀",t:520}, 襄阳:{o:"吴",t:480}, 成都:{o:"蜀",t:1260}, 建业:{o:"吴",t:940} },
      events: [{ kind:"battle", faction:"魏", text:"魏 自洛阳出兵 540,攻陷 长安" }] },
    { tick: 12, cities: { 长安:{o:"魏",t:780}, 洛阳:{o:"蜀",t:320}, 邺城:{o:"魏",t:1140}, 宛城:{o:"蜀",t:540}, 襄阳:{o:"吴",t:540}, 成都:{o:"蜀",t:1100}, 建业:{o:"吴",t:1000} },
      events: [{ kind:"battle", faction:"蜀", text:"蜀+吴 协同 攻克洛阳!曹操败退" }] },
    { tick: 16, cities: { 长安:{o:"魏",t:520}, 洛阳:{o:"蜀",t:480}, 邺城:{o:"蜀",t:240}, 宛城:{o:"蜀",t:620}, 襄阳:{o:"吴",t:600}, 成都:{o:"蜀",t:1180}, 建业:{o:"吴",t:1060} },
      events: [{ kind:"battle", faction:"蜀", text:"蜀 自洛阳偷袭 邺城,得手" }] },
    { tick: 21, cities: { 长安:{o:"蜀",t:280}, 洛阳:{o:"蜀",t:520}, 邺城:{o:"蜀",t:300}, 宛城:{o:"蜀",t:660}, 襄阳:{o:"吴",t:640}, 成都:{o:"蜀",t:1240}, 建业:{o:"吴",t:1100} },
      events: [{ kind:"battle", faction:"蜀", text:"蜀 收复长安 — 曹魏元气大伤" }] },
    { tick: 23, cities: { 长安:{o:"蜀",t:320}, 洛阳:{o:"蜀",t:540}, 邺城:{o:"蜀",t:360}, 宛城:{o:"蜀",t:680}, 襄阳:{o:"蜀",t:280}, 成都:{o:"蜀",t:1260}, 建业:{o:"蜀",t:160} },
      events: [{ kind:"battle", faction:"蜀", text:"蜀 全取建业,孙权降 — 终局" }] },
  ],
};

// ── Component ────────────────────────────────────────────────
function HeroBattle({ mode = "auto", liveEndpoint = "/v1/lobby/status", replayEndpoint = "/api/battles/latest" }) {
  const [resolvedMode, setResolvedMode] = React.useState("demo");
  const [state, setState] = React.useState(HB_initSynth);
  const [tick, setTick] = React.useState(1);
  const [attack, setAttack] = React.useState(null);
  const [log, setLog] = React.useState([]);
  const [paused, setPaused] = React.useState(false);
  const [replay, setReplay] = React.useState(null);   // { battle_id, ticks, idx, winner }
  const [liveMeta, setLiveMeta] = React.useState(null); // { game_id }
  const [previewFallback, setPreviewFallback] = React.useState(false);

  // ── Mode resolver: try live → replay → demo ────────────────
  React.useEffect(() => {
    let cancelled = false;
    async function resolve() {
      if (mode === "demo") { setResolvedMode("demo"); setPreviewFallback(false); return; }

      // try LIVE
      if (mode === "auto" || mode === "live") {
        try {
          const r = await fetch(liveEndpoint, { signal: AbortSignal.timeout(2000) });
          if (r.ok) {
            const d = await r.json();
            if (d?.status === "active" && Array.isArray(d.cities) && d.cities.length) {
              if (cancelled) return;
              const next = {};
              d.cities.forEach((c) => { next[c.name] = { owner: c.owner, troops: c.troops, flash: 0 }; });
              setState(next);
              setTick(d.tick || 0);
              setLiveMeta({ game_id: d.game_id });
              setResolvedMode("live");
              setPreviewFallback(false);
              return;
            }
          }
        } catch {}
        if (mode === "live") {
          // forced live but unreachable → preview-fallback (run demo engine, label "实时")
          if (!cancelled) { setResolvedMode("live"); setPreviewFallback(true); }
          return;
        }
      }

      // try REPLAY
      if (mode === "auto" || mode === "replay") {
        try {
          const r = await fetch(replayEndpoint, { signal: AbortSignal.timeout(2000) });
          if (r.ok) {
            const d = await r.json();
            if (d?.ticks && d.ticks.length) {
              if (cancelled) return;
              setReplay({ ...d, idx: 0 });
              setResolvedMode("replay");
              setPreviewFallback(false);
              return;
            }
          }
        } catch {}
        if (mode === "replay") {
          if (!cancelled) {
            setReplay({ ...HB_MOCK_REPLAY, idx: 0 });
            setResolvedMode("replay");
            setPreviewFallback(true);
          }
          return;
        }
      }

      // fallback: DEMO
      if (!cancelled) { setResolvedMode("demo"); setPreviewFallback(false); }
    }
    resolve();
    return () => { cancelled = true; };
  }, [mode, liveEndpoint, replayEndpoint]);

  // ── Demo engine ────────────────────────────────────────────
  React.useEffect(() => {
    const runDemo = resolvedMode === "demo" || (resolvedMode === "live" && previewFallback);
    if (!runDemo || paused) return;
    const id = setInterval(() => {
      setState((prev) => {
        const next = JSON.parse(JSON.stringify(prev));
        Object.keys(next).forEach((k) => {
          if (next[k].owner) next[k].troops = Math.min(2200, next[k].troops + 12 + Math.floor(Math.random() * 22));
          next[k].flash = Math.max(0, next[k].flash - 1);
        });
        const a = HB_pickAttack(next);
        if (a) {
          const defPower = next[a.tgt].troops;
          const atkPower = a.troops + Math.floor(Math.random() * 200 - 100);
          const win = atkPower > defPower;
          let row;
          if (win) {
            next[a.src].troops -= a.troops;
            next[a.tgt].owner = a.atkFaction;
            next[a.tgt].troops = Math.floor(a.troops * 0.75);
            next[a.tgt].flash = 3;
            row = { kind:"battle", faction:a.atkFaction, text:`${a.atkFaction} 自 ${a.src} 出兵 ${a.troops},攻陷 ${a.tgt}` };
          } else {
            next[a.src].troops -= Math.floor(a.troops * 0.6);
            next[a.tgt].troops = Math.max(80, Math.floor(next[a.tgt].troops * 0.5));
            next[a.tgt].flash = 2;
            row = { kind:"battle", faction:a.defFaction || a.atkFaction, text:`${a.tgt} 守城成功,${a.atkFaction} 退兵` };
          }
          const diplo = HB_pickDiplo();
          setAttack(a);
          setLog((lg) => [...(diplo ? [row, diplo] : [row]), ...lg].slice(0, 5));
          setTimeout(() => setAttack(null), 950);
        }
        return next;
      });
      setTick((t) => t + 1);
    }, 2500);
    return () => clearInterval(id);
  }, [resolvedMode, previewFallback, paused]);

  // ── Live poller ────────────────────────────────────────────
  React.useEffect(() => {
    if (resolvedMode !== "live" || previewFallback || paused) return;
    const id = setInterval(async () => {
      try {
        const r = await fetch(liveEndpoint, { signal: AbortSignal.timeout(2000) });
        if (!r.ok) return;
        const d = await r.json();
        if (!Array.isArray(d.cities)) return;
        const next = {};
        d.cities.forEach((c) => {
          next[c.name] = { owner: c.owner, troops: c.troops, flash: state[c.name]?.flash || 0 };
        });
        setState(next);
        setTick(d.tick || 0);
        if (Array.isArray(d.events) && d.events.length) {
          setLog((lg) => {
            const seen = new Set(lg.map((e) => e.id));
            const fresh = d.events.filter((e) => !seen.has(e.id || `${e.tick}|${e.text}`)).map((e) => ({
              kind: e.kind || "battle", faction: e.faction, text: e.text, id: e.id || `${e.tick}|${e.text}`,
            }));
            return [...fresh, ...lg].slice(0, 5);
          });
        }
      } catch {}
    }, 2500);
    return () => clearInterval(id);
  }, [resolvedMode, previewFallback, paused, liveEndpoint]);

  // ── Replay player ──────────────────────────────────────────
  React.useEffect(() => {
    if (resolvedMode !== "replay" || !replay || paused) return;
    const id = setInterval(() => {
      setReplay((meta) => {
        if (!meta) return meta;
        const nextIdx = (meta.idx + 1) % meta.ticks.length;
        const t = meta.ticks[nextIdx];
        const next = {};
        Object.entries(t.cities).forEach(([k, v]) => { next[k] = { owner: v.o, troops: v.t, flash: 2 }; });
        setState(next);
        setTick(t.tick);
        if (t.events && t.events.length) {
          setLog((lg) => [...t.events.map((e) => ({ ...e })), ...lg].slice(0, 5));
        }
        return { ...meta, idx: nextIdx };
      });
    }, 2000);
    return () => clearInterval(id);
  }, [resolvedMode, replay?.battle_id, paused]);

  // ── Render ─────────────────────────────────────────────────
  const W = 540, H = 320;

  // Mode pill content
  let modePill, modeCls;
  if (resolvedMode === "live") {
    modePill = previewFallback ? "● 实时 · 待接入" : `● 实时 · Game #${liveMeta?.game_id || "?"}`;
    modeCls = previewFallback ? "hb-pill hb-pill-dim" : "hb-pill hb-pill-live";
  } else if (resolvedMode === "replay") {
    const total = replay?.ticks?.length || 0;
    const idx = replay?.idx ?? 0;
    modePill = `↻ 回放 · #${replay?.battle_id || "?"} · ${idx + 1}/${total}`;
    modeCls = "hb-pill hb-pill-replay";
  } else {
    modePill = "○ 演示";
    modeCls = "hb-pill hb-pill-demo";
  }

  return (
    <div className="hb-wrap">
      <div className="hb-mapbox">
        <div className={modeCls}>{modePill}</div>

        <svg viewBox={`0 0 ${W} ${H}`}>
          <g fill="none" stroke="#c2b591" strokeWidth="1.5" opacity="0.55">
            <path d={`M 20 ${H*0.42} Q ${W*0.25} ${H*0.22}, ${W*0.55} ${H*0.46} T ${W-15} ${H*0.55}`} />
            <path d={`M 30 ${H*0.82} Q ${W*0.32} ${H*0.92}, ${W*0.7} ${H*0.78}`} opacity="0.55" />
          </g>
          <ellipse cx={W*0.55} cy={H*0.45} rx={W*0.45} ry={H*0.35} fill="#1f1a16" opacity="0.025" />

          <g stroke="#d3c6a8" strokeWidth="1" strokeDasharray="2 3">
            {Object.entries(HB_ADJ).flatMap(([from, tos]) =>
              tos.map((to) => {
                const a = HB_CITIES.find((c) => c.id === from);
                const b = HB_CITIES.find((c) => c.id === to);
                if (!a || !b || a.id > b.id) return null;
                return <line key={from + "-" + to} x1={a.x * W} y1={a.y * H} x2={b.x * W} y2={b.y * H} />;
              })
            )}
          </g>

          {attack && (() => {
            const a = HB_CITIES.find((c) => c.id === attack.src);
            const b = HB_CITIES.find((c) => c.id === attack.tgt);
            const c = HB_FACTION_HEX[attack.atkFaction];
            return (
              <g>
                <line x1={a.x * W} y1={a.y * H} x2={b.x * W} y2={b.y * H}
                      stroke={c} strokeWidth="2.5" strokeDasharray="6 4">
                  <animate attributeName="stroke-dashoffset" from="0" to="-20" dur="0.9s" repeatCount="indefinite" />
                </line>
                <circle cx={b.x * W} cy={b.y * H} r="14" fill="none" stroke={c} strokeWidth="2">
                  <animate attributeName="r" from="6" to="24" dur="0.95s" repeatCount="indefinite" />
                  <animate attributeName="opacity" from="1" to="0" dur="0.95s" repeatCount="indefinite" />
                </circle>
              </g>
            );
          })()}

          {HB_CITIES.map((c) => {
            const s = state[c.id] || { owner: null, troops: 0, flash: 0 };
            const owner = s.owner;
            const color = owner ? HB_FACTION_HEX[owner] : "#94887a";
            return (
              <g key={c.id} transform={`translate(${c.x * W}, ${c.y * H})`}>
                {s.flash > 0 && (
                  <circle r="20" fill="none" stroke={color} strokeWidth="1.5" opacity="0.7">
                    <animate attributeName="r" from="10" to="28" dur="1s" repeatCount="indefinite" />
                    <animate attributeName="opacity" from="0.7" to="0" dur="1s" repeatCount="indefinite" />
                  </circle>
                )}
                <rect x="-9" y="-9" width="18" height="18" fill={color} stroke="#1f1a16" strokeWidth="1" />
                <rect x="-12" y="-12" width="24" height="24" fill="none" stroke={color} strokeWidth="0.8" opacity="0.4" />
                <text y="-18" textAnchor="middle" fontSize="12" fill="#1f1a16"
                      fontFamily="'Noto Serif SC', serif" fontWeight="600" letterSpacing="1">
                  {c.id}
                </text>
                <text y="26" textAnchor="middle" fontSize="10" fill={color}
                      fontFamily="'JetBrains Mono', monospace" fontWeight="600">
                  {s.troops}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      <div className="hb-hud">
        <div className="hb-tick">
          <span className="hb-tick-label">TICK</span>
          <span className="hb-tick-num">{String(tick).padStart(3, "0")}</span>
        </div>
        <div className="hb-factions">
          {Object.entries(HB_FACTIONS).map(([k, f]) => {
            const ct = HB_CITIES.filter((c) => state[c.id]?.owner === k).length;
            const tt = HB_CITIES.filter((c) => state[c.id]?.owner === k).reduce((s, c) => s + (state[c.id]?.troops || 0), 0);
            return (
              <div key={k} className="hb-faction" style={{ "--fc": HB_FACTION_HEX[k] }}>
                <span className="hb-fdot" />
                <span className="hb-fname">{f.leader}</span>
                <span className="hb-fmeta">{ct}城·{tt}</span>
              </div>
            );
          })}
        </div>
        <div className="hb-ctrl">
          <button className="hb-btn" onClick={() => setPaused((p) => !p)} title={paused ? "play" : "pause"}>
            {paused ? "▶" : "❚❚"}
          </button>
        </div>
      </div>

      <div className="hb-log">
        {log.length === 0 && <div className="hb-log-empty">战事将启…</div>}
        {log.map((e, i) => {
          const fc = HB_FACTION_HEX[e.faction] || "#94887a";
          return (
            <div key={i} className="hb-log-row" style={{ "--ec": fc, opacity: 1 - i * 0.18 }}>
              <span className="hb-log-kind">{e.kind === "diplo" ? "✉" : "⚔"}</span>
              <span>{e.text}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export { HeroBattle };
