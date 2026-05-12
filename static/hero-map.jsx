// ═══════════════════════════════════════════════════════════════
// hero-map.jsx — Real-time battle map (data-driven)
// ═══════════════════════════════════════════════════════════════

// Adjacency edges for the SVG (matching backend CITY_ADJACENCY)
const HM_EDGES = [
  ["洛阳","长安"],["洛阳","邺城"],["洛阳","宛城"],
  ["长安","宛城"],["长安","成都"],
  ["宛城","襄阳"],
  ["襄阳","成都"],["襄阳","建业"],
];

function HeroMap({ theme, lang, cities, events, diplomacy, tick, status, winner, agents }) {
  const W = 520, H = 340;

  const isInk = theme === "ink";
  const isCyber = theme === "cyber";
  const mapBg = isCyber ? "#080b0a" : isInk ? "#fbf6ec" : "#1a140e";
  const gridColor = isCyber ? "#172220" : isInk ? "#e8e0d2" : "#2a1f14";
  const labelColor = isInk ? "#1a1614" : isCyber ? "#c8e8d8" : "#e8d8b0";

  // City positions (relative coords in 0..1 box)
  const CITY_POS = {
    "长安":[0.18,0.28],"洛阳":[0.50,0.22],"邺城":[0.74,0.14],
    "宛城":[0.42,0.48],"襄阳":[0.50,0.66],
    "成都":[0.16,0.72],"建业":[0.84,0.58],
  };

  // Build city lookup from data
  const cityMap = {};
  (cities || []).forEach(c => { cityMap[c.name] = c; });

  // Build faction stats
  const factionStats = {};
  (cities || []).forEach(c => {
    if (!c.owner) return;
    if (!factionStats[c.owner]) factionStats[c.owner] = { cities: 0, troops: 0 };
    factionStats[c.owner].cities += 1;
    factionStats[c.owner].troops += (c.troops || 0);
  });

  // Check if a faction has joined (is listed in agents)
  const factionJoined = {};
  (agents || []).forEach(a => { factionJoined[a.faction] = a.name; });

  return (
    <div className="hm-wrap">
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", display: "block", background: mapBg }}>
        {/* grid for cyber theme */}
        {isCyber && (
          <g stroke={gridColor} strokeWidth="0.5">
            {Array.from({ length: 14 }).map((_, i) => (
              <line key={"v" + i} x1={i * 40} y1="0" x2={i * 40} y2={H} />
            ))}
            {Array.from({ length: 9 }).map((_, i) => (
              <line key={"h" + i} x1="0" y1={i * 40} x2={W} y2={i * 40} />
            ))}
          </g>
        )}
        {/* landmass strokes */}
        {!isCyber && (
          <g fill="none" stroke={gridColor} strokeWidth={isInk ? 1 : 1.2}>
            <path d={`M 30 ${H * 0.4} Q ${W * 0.3} ${H * 0.2}, ${W * 0.55} ${H * 0.45} T ${W - 20} ${H * 0.6}`} />
            <path d={`M 50 ${H * 0.78} Q ${W * 0.35} ${H * 0.85}, ${W * 0.7} ${H * 0.78}`} opacity="0.6" />
          </g>
        )}

        {/* edges */}
        <g stroke={isCyber ? "#1f3a32" : isInk ? "#cfc4ae" : "#3a2a1a"} strokeWidth="1.5" strokeDasharray={isCyber ? "0" : "4 3"}>
          {HM_EDGES.map(([a, b]) => {
            const pa = CITY_POS[a], pb = CITY_POS[b];
            return <line key={a + "-" + b} x1={pa[0] * W} y1={pa[1] * H} x2={pb[0] * W} y2={pb[1] * H} />;
          })}
        </g>

        {/* cities */}
        {Object.entries(CITY_POS).map(([name, [cx, cy]]) => {
          const c = cityMap[name];
          const owner = c ? c.owner : null;
          const troops = c ? c.troops : "?";
          const f = owner ? FACTIONS[owner] : null;
          const baseColor = f ? f.color : (isInk ? "#888" : isCyber ? "#5a6e66" : "#7a6a4a");
          const r = isCyber ? 8 : 12;

          const sty = isCyber
            ? { fill: "#0d1110", stroke: baseColor, strokeWidth: 2 }
            : isInk
              ? { fill: baseColor, stroke: "#1a1614", strokeWidth: 1.5 }
              : { fill: baseColor, stroke: "#1c1410", strokeWidth: 1.5 };

          return (
            <g key={name} transform={`translate(${cx * W}, ${cy * H})`}>
              {isCyber
                ? <rect x={-r} y={-r} width={r * 2} height={r * 2} {...sty} />
                : <circle r={r} {...sty} />
              }
              <text y={isCyber ? -12 : -17} textAnchor="middle"
                fontSize={isCyber ? 9 : 12}
                fill={labelColor}
                fontFamily={isCyber ? "'JetBrains Mono', monospace" : "'Noto Serif SC', serif"}
                fontWeight={isInk ? 600 : 500}>
                {name}
              </text>
              <text y={isCyber ? 22 : 25} textAnchor="middle"
                fontSize={isCyber ? 9 : 11}
                fill={owner ? (FACTIONS[owner] || {}).color || baseColor : (isInk ? "#888" : "#7a6a4a")}
                fontFamily="'JetBrains Mono', monospace">
                {troops}
              </text>
            </g>
          );
        })}
      </svg>

      {/* HUD strip */}
      <div className="hm-hud">
        <div className="hm-tick">
          <span className="hm-tick-label">{lang === "中" ? "回合" : "TICK"}</span>
          <span className="hm-tick-num">{String(tick || 0).padStart(3, "0")}</span>
        </div>
        {status === "finished" && winner && (
          <div className="hm-tick" style={{ marginLeft: 16 }}>
            <span className="hm-tick-label">{lang === "中" ? "胜者" : "WINNER"}</span>
            <span className="hm-tick-num" style={{ color: (FACTIONS[winner] || {}).color || "var(--gold)" }}>
              {winner} {lang === "中" ? FACTIONS[winner].leader : ""}
            </span>
          </div>
        )}
        <div className="hm-factions">
          {Object.entries(FACTIONS).map(([k, f]) => {
            const s = factionStats[k] || { cities: 0, troops: 0 };
            const joined = factionJoined[k];
            const dim = joined ? 1 : 0.4;
            return (
              <div key={k} className="hm-faction" style={{ "--fc": f.color, opacity: dim }}>
                <span className="hm-fdot" />
                <span className="hm-fname">{f.leader}</span>
                <span className="hm-fmeta">
                  {s.cities}城 · {s.troops}兵
                  {!joined ? " (" + (lang === "中" ? "空缺" : "open") + ")" : ""}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* event log */}
      <div className="hm-log">
        {(events || []).length === 0 && (diplomacy || []).length === 0 && (
          <div className="hm-log-empty">{lang === "中" ? "等待对战开始…" : "Awaiting battle…"}</div>
        )}
        {(diplomacy || []).slice(-3).map((d, i) => {
          const fc = (FACTIONS[d.from_faction] || {}).color || "var(--ink-mute)";
          return (
            <div key={"d" + i} className="hm-log-row" style={{ "--ec": fc }}>
              <span className="hm-log-dot" />
              <span className="hm-log-kind">✉</span>
              <span className="hm-log-text">
                [{d.from_faction}]「{d.message}」
              </span>
            </div>
          );
        })}
        {(events || []).slice(-5).map((e, i) => {
          let text, kind, faction;
          if (e.result === "captured") {
            text = (lang === "中"
              ? e.captured_by + " 攻占 " + e.city
              : e.captured_by + " captured " + e.city);
            kind = "⚔";
            faction = e.captured_by;
          } else if (e.result === "defended") {
            text = (lang === "中"
              ? e.defended_by + " 守住 " + e.city
              : e.defended_by + " defended " + e.city);
            kind = "🛡";
            faction = e.defended_by;
          } else if (e.type === "recruit") {
            text = e.faction + " 在 " + e.city + " 招募";
            kind = "📋";
            faction = e.faction;
          } else if (e.type === "march") {
            text = e.faction + " 行军 " + (e.from || "") + "→" + (e.to || "");
            kind = "🚶";
            faction = e.faction;
          } else { return null; }
          const fc = (FACTIONS[faction] || {}).color || "var(--ink-mute)";
          return (
            <div key={"e" + i} className="hm-log-row" style={{ "--ec": fc }}>
              <span className="hm-log-dot" />
              <span className="hm-log-kind">{kind}</span>
              <span className="hm-log-text">{text}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

window.HeroMap = HeroMap;
