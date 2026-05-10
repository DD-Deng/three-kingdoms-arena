// ═══════════════════════════════════════════════════════════════
// hero-map.jsx — Live battle animation (themed by prop)
// ═══════════════════════════════════════════════════════════════

const HM_USE_REDUCER = (() => {});

// Adjacency (which city can attack which)
const HM_ADJ = {
  "长安": ["洛阳", "成都", "宛城"],
  "洛阳": ["长安", "宛城"],
  "宛城": ["长安", "洛阳", "襄阳", "成都"],
  "襄阳": ["宛城", "成都", "建业"],
  "成都": ["长安", "宛城", "襄阳"],
  "建业": ["襄阳"],
};

function HM_initState() {
  const s = {};
  CITIES.forEach((c) => {
    s[c.id] = {
      owner: c.faction,
      troops: c.faction ? 1000 + Math.floor(Math.random() * 200) : 600 + Math.floor(Math.random() * 200),
      defense: 0,
      flash: 0,
    };
  });
  return s;
}

// Pick a sensible attack
function HM_pickAttack(state) {
  const owned = CITIES.filter((c) => state[c.id].owner);
  const ordered = owned.sort(() => Math.random() - 0.5);
  for (const src of ordered) {
    if (state[src.id].troops < 250) continue;
    const adj = HM_ADJ[src.id] || [];
    const targets = adj
      .map((n) => CITIES.find((c) => c.id === n))
      .filter((c) => c && state[c.id].owner !== state[src.id].owner);
    if (targets.length === 0) continue;
    const tgt = targets[Math.floor(Math.random() * targets.length)];
    return {
      src: src.id,
      tgt: tgt.id,
      atkFaction: state[src.id].owner,
      defFaction: state[tgt.id].owner,
      troops: Math.floor(state[src.id].troops * (0.4 + Math.random() * 0.3)),
    };
  }
  return null;
}

function HeroMap({ theme, lang }) {
  const [state, setState] = React.useState(HM_initState);
  const [tick, setTick] = React.useState(1);
  const [attack, setAttack] = React.useState(null);
  const [eventLog, setEventLog] = React.useState([]);
  const [paused, setPaused] = React.useState(false);

  // Diplomacy event injector — fires occasionally between battles
  const maybeDiplomacy = React.useCallback(() => {
    if (Math.random() > 0.35) return null;
    const factions = ["蜀", "魏", "吴"];
    const a = factions[Math.floor(Math.random() * 3)];
    let b = factions[Math.floor(Math.random() * 3)];
    while (b === a) b = factions[Math.floor(Math.random() * 3)];
    const kinds = [
      { k: "alliance_propose", cn: `${a} → ${b}:遣使求盟`, en: `${a} → ${b}: alliance_propose` },
      { k: "alliance_accept",  cn: `${b} → ${a}:歃血为盟`, en: `${b} → ${a}: alliance_accept` },
      { k: "declare_war",      cn: `${a} 宣战 ${b}`,        en: `${a} declared war on ${b}` },
      { k: "alliance_break",   cn: `${a} 单方面撕毁与 ${b} 之盟`, en: `${a} broke alliance with ${b}` },
    ];
    const e = kinds[Math.floor(Math.random() * kinds.length)];
    return { tick, text: lang === "中" ? e.cn : e.en, kind: "diplo", faction: a };
  }, [tick, lang]);

  React.useEffect(() => {
    if (paused) return;
    const id = setInterval(() => {
      setState((prev) => {
        const next = JSON.parse(JSON.stringify(prev));
        // soft regen / decay flash
        Object.keys(next).forEach((k) => {
          if (next[k].owner) next[k].troops = Math.min(2200, next[k].troops + 15 + Math.floor(Math.random() * 25));
          next[k].flash = Math.max(0, next[k].flash - 1);
        });
        // pick + execute attack
        const a = HM_pickAttack(next);
        if (a) {
          const defPower = next[a.tgt].troops * (1 + next[a.tgt].defense * 0.2);
          const atkPower = a.troops + Math.floor(Math.random() * 200 - 100);
          const atkWins = atkPower > defPower;
          let evt;
          if (atkWins) {
            next[a.src].troops -= a.troops;
            next[a.tgt].owner = a.atkFaction;
            next[a.tgt].troops = Math.floor(a.troops * 0.75);
            next[a.tgt].defense = 0;
            next[a.tgt].flash = 3;
            const v = lang === "中"
              ? `${a.atkFaction} 自 ${a.src} 出兵 ${a.troops},攻陷 ${a.tgt}`
              : `${FACTIONS[a.atkFaction].en} took ${a.tgt} from ${a.src} (${a.troops} troops)`;
            evt = { tick: prev.__tick, text: v, kind: "win", faction: a.atkFaction };
          } else {
            next[a.src].troops -= Math.floor(a.troops * 0.6);
            next[a.tgt].troops = Math.max(100, Math.floor(next[a.tgt].troops * 0.5));
            next[a.tgt].flash = 2;
            const v = lang === "中"
              ? `${a.tgt} 守城成功,${a.atkFaction} 退兵`
              : `${a.tgt} held — ${FACTIONS[a.atkFaction].en} repelled`;
            evt = { tick: prev.__tick, text: v, kind: "hold", faction: a.defFaction || a.atkFaction };
          }
          setAttack(a);
          const diplo = maybeDiplomacy();
          setEventLog((log) => {
            const entries = [evt, ...(diplo ? [diplo] : [])];
            return [...entries, ...log].slice(0, 5);
          });
          setTimeout(() => setAttack(null), 900);
        }
        return next;
      });
      setTick((t) => t + 1);
    }, 2400);
    return () => clearInterval(id);
  }, [paused, lang]);

  // theme styling tokens
  const isInk = theme === "ink";
  const isCyber = theme === "cyber";

  const cityStyle = (city) => {
    const owner = state[city.id].owner;
    const f = owner ? FACTIONS[owner] : null;
    const baseColor = f ? f.color : (isInk ? "#666" : isCyber ? "#5a6e66" : "#7a6a4a");
    if (isCyber) {
      return {
        fill: "#0d1110",
        stroke: baseColor,
        strokeWidth: 1.5,
      };
    }
    if (isInk) {
      return { fill: baseColor, stroke: "#1a1614", strokeWidth: 1 };
    }
    return { fill: baseColor, stroke: "#1c1410", strokeWidth: 1.5 };
  };

  const labelColor = isInk ? "#1a1614" : isCyber ? "#c8e8d8" : "#e8d8b0";

  // SVG dims
  const W = 520, H = 340;

  // Map background
  const mapBg = isCyber ? "#080b0a" : isInk ? "#fbf6ec" : "#1a140e";
  const gridColor = isCyber ? "#172220" : isInk ? "#e8e0d2" : "#2a1f14";

  return (
    <div className="hm-wrap">
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", display: "block", background: mapBg }}>
        {/* grid */}
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
        {!isCyber && (
          // subtle landmass strokes
          <g fill="none" stroke={gridColor} strokeWidth={isInk ? 1 : 1.2}>
            <path d={`M 30 ${H * 0.4} Q ${W * 0.3} ${H * 0.2}, ${W * 0.55} ${H * 0.45} T ${W - 20} ${H * 0.6}`} />
            <path d={`M 50 ${H * 0.78} Q ${W * 0.35} ${H * 0.85}, ${W * 0.7} ${H * 0.78}`} opacity="0.6" />
          </g>
        )}

        {/* edges between adjacent cities */}
        <g stroke={isCyber ? "#1f3a32" : isInk ? "#cfc4ae" : "#3a2a1a"} strokeWidth="1" strokeDasharray={isCyber ? "0" : "2 3"}>
          {Object.entries(HM_ADJ).flatMap(([from, tos]) =>
            tos.map((to) => {
              const a = CITIES.find((c) => c.id === from);
              const b = CITIES.find((c) => c.id === to);
              if (!a || !b || a.id > b.id) return null;
              return <line key={from + "-" + to} x1={a.x * W} y1={a.y * H} x2={b.x * W} y2={b.y * H} />;
            })
          )}
        </g>

        {/* attack arrow */}
        {attack && (() => {
          const a = CITIES.find((c) => c.id === attack.src);
          const b = CITIES.find((c) => c.id === attack.tgt);
          const stroke = FACTIONS[attack.atkFaction].color;
          return (
            <g>
              <line x1={a.x * W} y1={a.y * H} x2={b.x * W} y2={b.y * H}
                    stroke={stroke} strokeWidth="2.5" strokeDasharray="6 4">
                <animate attributeName="stroke-dashoffset" from="0" to="-20" dur="0.9s" repeatCount="indefinite" />
              </line>
              <circle cx={b.x * W} cy={b.y * H} r="14" fill="none" stroke={stroke} strokeWidth="2">
                <animate attributeName="r" from="6" to="22" dur="0.9s" repeatCount="indefinite" />
                <animate attributeName="opacity" from="1" to="0" dur="0.9s" repeatCount="indefinite" />
              </circle>
            </g>
          );
        })()}

        {/* cities */}
        {CITIES.map((c) => {
          const s = state[c.id];
          const sty = cityStyle(c);
          const pulse = s.flash > 0;
          const r = isCyber ? 6 : 10;
          return (
            <g key={c.id} transform={`translate(${c.x * W}, ${c.y * H})`}>
              {pulse && (
                <circle r={r + 8} fill="none" stroke={sty.fill} strokeWidth="1.5" opacity="0.6">
                  <animate attributeName="r" from={r + 4} to={r + 18} dur="1s" repeatCount="indefinite" />
                  <animate attributeName="opacity" from="0.7" to="0" dur="1s" repeatCount="indefinite" />
                </circle>
              )}
              {isCyber ? (
                <rect x={-r} y={-r} width={r * 2} height={r * 2} {...sty} />
              ) : (
                <circle r={r} {...sty} />
              )}
              <text y={isCyber ? -10 : -14} textAnchor="middle"
                    fontSize={isCyber ? 9 : 11}
                    fill={labelColor}
                    fontFamily={isCyber ? "'JetBrains Mono', monospace" : "'Noto Serif SC', serif"}
                    fontWeight={isInk ? 600 : 500}>
                {lang === "中" ? c.id : c.en}
              </text>
              <text y={isCyber ? 18 : 22} textAnchor="middle"
                    fontSize={isCyber ? 9 : 10}
                    fill={s.owner ? FACTIONS[s.owner].color : (isInk ? "#888" : "#7a6a4a")}
                    fontFamily="'JetBrains Mono', monospace">
                {s.troops}
              </text>
            </g>
          );
        })}
      </svg>

      {/* HUD strip */}
      <div className="hm-hud">
        <div className="hm-tick">
          <span className="hm-tick-label">{lang === "中" ? "回合" : "TICK"}</span>
          <span className="hm-tick-num">{String(tick).padStart(3, "0")}</span>
        </div>
        <div className="hm-ctrl">
          <button className="hm-btn" onClick={() => setPaused((p) => !p)} title={paused ? "play" : "pause"}>
            {paused ? "▶" : "❚❚"}
          </button>
        </div>
        <div className="hm-factions">
          {Object.entries(FACTIONS).map(([k, f]) => {
            const cities = CITIES.filter((c) => state[c.id].owner === k).length;
            const troops = CITIES.filter((c) => state[c.id].owner === k).reduce((s, c) => s + state[c.id].troops, 0);
            return (
              <div key={k} className="hm-faction" style={{ "--fc": f.color }}>
                <span className="hm-fdot" />
                <span className="hm-fname">{lang === "中" ? f.leader : f.leaderEn}</span>
                <span className="hm-fmeta">{cities}城 · {troops}</span>
              </div>
            );
          })}
        </div>
      </div>

      <div className="hm-log">
        {eventLog.length === 0 && (
          <div className="hm-log-empty">{lang === "中" ? "战事将启…" : "Awaiting orders…"}</div>
        )}
        {eventLog.map((e, i) => {
          const fc = (FACTIONS[e.faction] && FACTIONS[e.faction].color) || "var(--ink-mute)";
          return (
            <div key={i} className="hm-log-row" style={{ "--ec": fc, opacity: 1 - i * 0.18 }}>
              <span className="hm-log-dot" />
              <span className="hm-log-kind">{e.kind === "diplo" ? "✉" : "⚔"}</span>
              <span className="hm-log-text">{e.text}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

window.HeroMap = HeroMap;
