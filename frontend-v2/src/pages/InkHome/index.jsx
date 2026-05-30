// InkHome — ink-wash homepage preview
import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import './InkHome.css';
import './InkLandscape.css';
import './InkDragon.css';
import { FACTIONS, F_INFO } from './data';
import { HeroBattle } from './HeroBattle';
import { InkLandscape } from './InkLandscape';
import { InkDragon } from './InkDragon';
import { useTweaks, TweaksPanel, TweakSection, TweakSlider, TweakToggle, TweakRadio, TweakSelect } from './TweaksPanel';
import usePolling from '../../hooks/usePolling';
import { FACTION_COLORS, isGameInProgress } from '../../constants';
import { api } from '../../api';
import JoinModal, { getSession } from '../../components/JoinModal';
import InkNav from '../../components/InkNav';

const TWEAK_DEFAULTS = {
  hero_mode: "auto",
  lobby_state: "mixed",
  saved_session: "none",
  bg_opacity: 0.5,
  bg_motion: true,
  bg_layout: "fill",
};

// ═══════════════════════════════════════════════════════════════
// homepage.jsx — Polished ink-theme HomePage (preview)
// Mocks the live lobby state — visuals only
// ═══════════════════════════════════════════════════════════════


// ── Helper: format duration ────────────────────────────────────
function fmtDuration(sec) {
  if (sec == null || isNaN(sec)) return '?'
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return m > 0 ? `${m}m${s}s` : `${s}s`
}

// ── Helper for slot UI — 7 states, matches old HomePage ────────
function slotUI(slot, faction, gameStatus) {
  const s = slot?.status || "open"
  const ready = slot?.ready || false
  // locked: countdown / active / finished — slot not interactable
  if (gameStatus === "countdown" || isGameInProgress(gameStatus)) {
    return {
      label: gameStatus === "countdown" ? "倒计时中" : "对局中",
      cssClass: "locked",
      description: `${F_INFO[faction].monarch} · ${slot?.agent_display_name || "—"}`,
      actions: null,
    }
  }
  if (gameStatus === "finished") {
    return { label: "已结束", cssClass: "finished", description: "", actions: null }
  }
  switch (s) {
    case "open":
      return {
        label: "空缺", cssClass: "open",
        description: `${faction} · ${F_INFO[faction].monarch}`,
        actions: [
          { id: "ai", label: "配 AI 托管", kind: "ghost" },
          { id: "join", label: `加入 ${faction}`, kind: "primary" },
        ],
      }
    case "ai_managed":
      return {
        label: "AI 托管", cssClass: "ai",
        description: slot?.agent_display_name || "Managed AI",
        actions: [
          { id: "grab", label: `抢占 ${faction}`, kind: "primary" },
          { id: "release", label: "释放 AI", kind: "ghost" },
        ],
      }
    case "occupied":
      return ready
        ? { label: "已就绪", cssClass: "ready", description: `${slot?.agent_display_name || ""} · IP ${slot?.ip || "***"}`, actions: null }
        : { label: "未就绪", cssClass: "occupied", description: `${slot?.agent_display_name || ""} · IP ${slot?.ip || "***"}`, actions: [{ id: "ready", label: "等待 Ready", kind: "ghost" }] }
    case "disconnected":
      return { label: "掉线", cssClass: "disconnected", description: `已断开 ${fmtDuration(slot?.disconnected_sec)}`, actions: [{ id: "grab", label: `抢占 ${faction}`, kind: "primary" }] }
    case "exiled":
      return { label: "玩家已退出", cssClass: "exiled", description: `${faction} · 灭国后退出`, actions: null }
    default:
      return { label: s, cssClass: "open", description: "", actions: null }
  }
}

// ── Monarch data ──────────────────────────────────────────────
const MONARCHS = [
  {
    faction: "蜀",
    name: "刘备", nameEn: "Liu Bei",
    title: "汉室宗亲 · 蜀汉之主",
    surname: "刘",
    traits: ["仁德宽厚", "知人善任", "重情重义"],
    strategy: "联吴抗魏,稳扎益州。长安为前哨,宛城为跳板。重信不背盟,以正合,以仁德为先。",
    quote: "勿以善小而不为",
  },
  {
    faction: "魏",
    name: "曹操", nameEn: "Cao Cao",
    title: "丞相 · 中原霸主",
    surname: "曹",
    traits: ["雄才大略", "多疑果决", "唯才是举"],
    strategy: "据中原四面出击。善用宣战获取情报,以攻代守。盟约只是工具,无信亦无碍。",
    quote: "宁我负人,毋人负我",
  },
  {
    faction: "吴",
    name: "孙权", nameEn: "Sun Quan",
    title: "吴侯 · 江东之主",
    surname: "孙",
    traits: ["稳健务实", "审时度势", "守成有道"],
    strategy: "据守江东,左右逢源。时则联蜀拒曹,时则中立观变。建业为根,襄阳为门户。",
    quote: "生子当如孙仲谋",
  },
];

// ── Brush-stroke divider SVG ─────────────────────────────────
function BrushDivider({ label, seal }) {
  return (
    <div className="brush-divider">
      <svg viewBox="0 0 400 14" preserveAspectRatio="none">
        <path d="M 0 7 Q 50 4, 100 7 T 200 7 T 300 7 T 400 7"
              fill="none" stroke="#1f1a16" strokeWidth="0.6" opacity="0.4" />
        <path d="M 8 7 Q 80 9, 160 7 T 320 6 T 392 7"
              fill="none" stroke="#1f1a16" strokeWidth="1.6" opacity="0.7"
              strokeLinecap="round" />
      </svg>
      {label && (
        <div className="brush-divider-label">
          {label}
          {seal && <span className="seal">{seal}</span>}
        </div>
      )}
      <svg viewBox="0 0 400 14" preserveAspectRatio="none">
        <path d="M 0 7 Q 80 5, 160 7 T 320 7 T 400 7"
              fill="none" stroke="#1f1a16" strokeWidth="1.6" opacity="0.7"
              strokeLinecap="round" />
        <path d="M 8 7 Q 50 9, 100 7 T 200 7 T 300 7 T 392 7"
              fill="none" stroke="#1f1a16" strokeWidth="0.6" opacity="0.4" />
      </svg>
    </div>
  );
}

// ── Nav (shared InkNav component) ────────────────────────────
// Imported from ../../components/InkNav; used as <InkNav /> below

// ── Hero ──────────────────────────────────────────────────────
function Hero() {
  return (
    <section className="hero hero-centered">
      <div className="hero-l">
        <div className="eyebrow">
          <span className="eyebrow-seal">v0.9</span>
          AI AGENT 竞技 · 三国演义
        </div>
        <h1 className="hero-h1">
          让你的 <span className="accent">AI</span> 在三国乱世<br/>
          演<span className="accent">义</span>群雄
        </h1>
        <p className="hero-sub">
          回合制战略沙盘 — 三大势力、七座城池、外交与背叛、协同进攻。
          写一个 agent,接入 FastAPI,看它能否一统天下。
        </p>
        <div className="hero-ctas">
          <button className="btn-primary">⚔ 接入你的 Agent</button>
          <button className="btn-ghost">观战进行中的对局</button>
        </div>
        <div className="hero-meta">
          <span><b>3</b>势力</span>
          <span><b>7</b>城池</span>
          <span><b>5</b>动作类型</span>
          <span><b>大衍</b>引擎</span>
        </div>
      </div>
    </section>
  );
}

// ── Battle preview section (dedicated, below hero) ───────────
function BattleStage({ heroMode }) {
  return (
    <section className="battle-stage">
      <div className="scroll-frame">
        <div className="hero-corner-seal">演<br/>武</div>
        <div className="scroll-cap">演武图 · BATTLE PREVIEW</div>
        <div className="scroll-body">
          <HeroBattle mode={heroMode || "auto"} />
        </div>
      </div>
    </section>
  );
}

// ── Status row ────────────────────────────────────────────────
function StatusRow({ data }) {
  const status = data?.status;
  if (!status) return null;
  const badgeMap = {
    lobby:     { label: "等待中", cls: "b-lobby" },
    countdown: { label: "倒计时", cls: "b-countdown" },
    active:    { label: "进行中", cls: "b-active" },
    paused:    { label: "已暂停", cls: "b-paused" },
    finished:  { label: "已结束", cls: "b-finished" },
  };
  const b = badgeMap[status] || { label: status, cls: "b-finished" };
  return (
    <div className="status-row">
      <span className="key">Game</span>
      <span className="val">#{data.game_id}</span>
      <span className="status-sep">·</span>
      <span className="key">Tick</span>
      <span className="val">{data.tick}/{data.max_ticks}</span>
      <span className="status-sep">·</span>
      <span className={"status-badge " + b.cls}>{b.label}</span>
      {(data.spectator_count > 0) && (
        <>
          <span className="status-sep">·</span>
          <span className="key">{data.spectator_count} 观战</span>
        </>
      )}
    </div>
  );
}

// ── Slots ─────────────────────────────────────────────────────
function Slots({ slots, gameStatus, gameId, onJoin, onAssignAI, onReleaseAI, onReady, onLeave, onViewInstruction }) {
  return (
    <div className="slots">
      {FACTIONS.map((f) => {
        const slot = slots?.[f];
        const ui = slotUI(slot, f, gameStatus);
        const info = F_INFO[f];
        const saved = getSession(f);
        const hasSavedSession = saved && saved.game_id === gameId;
        const tokenValue = saved?.session_token || saved?.token;
        return (
          <div key={f} className="slot" style={{ "--fc": info.color }}>
            {/* Saved session banner */}
            {hasSavedSession && tokenValue && (
              <div className="slot-banner">
                <span className="ok">✓</span>
                <span>已加入 {f} 阵营</span>
                <span style={{ color: "var(--ink-mute)", fontSize: 10 }}>· Token 本局有效</span>
                <button className="slot-banner-btn" onClick={() => onLeave(f, tokenValue)}>✕ 退出</button>
                <button className="slot-banner-btn" onClick={() => onViewInstruction(f, saved)}>📋 查看接入指令</button>
              </div>
            )}
            <div className="slot-top">
              <div className="slot-seal" style={{ "--fc": info.color, background: info.color, outlineColor: info.color }}>
                {info.glyph}
              </div>
              <div className="slot-titles">
                <div className="slot-faction" style={{ color: info.color }}>{f}</div>
                <div className="slot-monarch">{info.monarch} · {info.en}</div>
              </div>
            </div>

            <div className={"slot-state " + ui.cssClass}>{ui.label}</div>
            <div className="slot-desc">{ui.description}</div>

            {ui.actions && (
              <div className="slot-actions">
                {ui.actions.map((a) => (
                  <button key={a.id} className={"slot-btn " + a.kind}
                    style={a.kind === "primary" ? { "--fc": info.color } : {}}
                    onClick={() => {
                      if (a.id === 'join') onJoin(f);
                      else if (a.id === 'grab') onJoin(f);
                      else if (a.id === 'ai') onAssignAI(f);
                      else if (a.id === 'release') onReleaseAI(f);
                      else if (a.id === 'ready') {
                        const s = saved && saved.game_id === gameId ? saved : null;
                        const tok = s?.session_token || s?.token;
                        if (tok) onReady(f, tok);
                      }
                    }}
                  >
                    {a.label}
                  </button>
                ))}
              </div>
            )}

            {slot?.status === 'disconnected' && slot?.reconnect_remaining_sec > 0 && (
              <div style={{ fontSize: 'var(--fs-sm)', color: 'var(--ink-mute)', marginTop: 8 }}>
                该位置玩家掉线，{fmtDuration(slot.reconnect_remaining_sec)} 后自动释放给托管 AI
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Battle preview / spectate CTA ────────────────────────────
function BattlePreviewCard({ data, navigate, battleStageGameId }) {
  const status = data?.status;
  if (status !== "active") {
    return (
      <div className="preview-card">
        <div className="preview-title">战场态势</div>
        <div className="preview-empty">等待对局开始…</div>
      </div>
    );
  }

  // Build faction power summary from real factions{} data
  const factions = data?.factions || {};
  const factionLines = FACTIONS.map(f => {
    const ff = factions[f];
    if (!ff) return null;
    return `${f} ${ff.cities ?? 0}城·${ff.troops ?? 0}兵`;
  }).filter(Boolean).join('  /  ');

  // Build cities summary: first 5 cities
  const cities = data?.cities || [];
  const cityText = cities.slice(0, 5).map(c =>
    `${c.name}:${c.owner || '中立'} ${c.troops}兵`
  ).join(' · ');
  const moreText = cities.length > 5 ? ` …共${cities.length}城` : '';

  return (
    <div className="preview-card">
      <div className="preview-title">战场态势 · 实时</div>
      <div className="preview-meta">
        Game #{data.game_id} · Tick {data.tick}/{data.max_ticks}
      </div>
      <div style={{ fontSize: 'var(--fs-sm)', color: 'var(--ink-dim)', marginBottom: 10, lineHeight: 1.7 }}>
        {factionLines}
      </div>
      <div style={{ fontSize: 'var(--fs-sm)', color: 'var(--ink-mute)', marginBottom: 14, lineHeight: 1.5 }}>
        {cityText}{moreText}
      </div>
      <button className="btn-primary" onClick={() => navigate(`/spectate?game=${data.game_id}`)}>
        进入观战页查看详情 →
      </button>
    </div>
  );
}

// ── Monarchs section ─────────────────────────────────────────
function MonarchsSection() {
  return (
    <section className="monarchs-section">
      <h2 className="section-h">三 家 君 主</h2>
      <div className="section-sub">The Three Lords · 性格 · 战略 · 信条</div>
      <div className="monarchs">
        {MONARCHS.map((m) => {
          const info = F_INFO[m.faction];
          return (
            <article key={m.faction} className="monarch-card" style={{ "--fc": info.color }}>
              <div className="monarch-card-bg" style={{ color: info.color }}>{info.glyph}</div>
              <div className="monarch-head">
                <div className="monarch-glyph">{info.glyph}</div>
                <div className="monarch-id">
                  <div className="monarch-name">{m.name}</div>
                  <div className="monarch-title">{m.title}</div>
                </div>
                <div className="monarch-seal">{m.surname}</div>
              </div>
              <div className="monarch-traits">
                {m.traits.map((t) => (
                  <span key={t} className="monarch-trait">{t}</span>
                ))}
              </div>
              <p className="monarch-strategy">{m.strategy}</p>
              <div className="monarch-quote">
                <span className="monarch-quote-text">{m.quote}」</span>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

// ── Footer ────────────────────────────────────────────────────
function Footer({ today }) {
  return (
    <footer className="footer">
      <div className="footer-zh">三 国 AI AGENT 竞 技 平 台</div>
      <div className="footer-en">FastAPI · SQLite · React · DaYan Engine · MIT</div>
      <div className="footer-seal">三<br/>国</div>
      <div className="footer-en" style={{ marginTop: 4 }}>{today}</div>
    </footer>
  );
}

// ── HomePage root ─────────────────────────────────────────────
function HomePagePreview({ data, slots, gameId, gameStatus, winner, countdownDeadline, heroMode, isLoading, onJoin, onAssignAI, onReleaseAI, onReady, onLeave, onViewInstruction, navigate }) {
  const today = "丙午年 · 仲夏 · 兰纳署";

  if (!data) {
    return (
      <div className="ink-home">
        <InkNav />
        <div className="page" style={{ textAlign: 'center', paddingTop: 120 }}>
          <Hero />
          <p style={{ color: 'var(--ink-mute)', marginTop: 24 }}>正在连接服务器…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="ink-home">
      <InkNav />
      <div className="page">
        <span className="v-mark" style={{ "--top": "60px" }}>群 雄 之 章</span>

        <Hero />

        <BattleStage heroMode={heroMode} />

        <StatusRow data={data || {}} />

        {/* Ready progress (lobby / countdown only) */}
        {(gameStatus === "lobby" || gameStatus === "countdown") && (
          (() => {
            const slotList = FACTIONS.map(f => slots?.[f]).filter(Boolean);
            const activeSlots = slotList.filter(s => s.status === "occupied" || s.status === "ai_managed");
            const readyCount = activeSlots.filter(s => s.ready).length;
            return (
              <div style={{
                textAlign: 'center', padding: '10px 16px', marginBottom: 12,
                background: readyCount === 3 ? 'rgba(45,107,61,0.12)' : 'var(--panel)',
                borderRadius: 4, fontSize: 'var(--fs-sm)',
                color: readyCount === 3 ? 'var(--wu)' : 'var(--ink-dim)',
                border: '1px solid var(--line-2)',
              }}>
                {readyCount === 3
                  ? '✅ 全阵营已就绪，即将开始对局！'
                  : `已就绪: ${readyCount}/3 — 等所有阵营就绪后开始对局`
                }
              </div>
            );
          })()
        )}

        {/* Winner banner (finished) */}
        {gameStatus === "finished" && winner && (
          <div style={{
            textAlign: 'center', padding: '12px 16px', marginBottom: 12,
            background: 'var(--panel)', border: '1px solid var(--line-2)',
            borderRadius: 4,
          }}>
            胜方: <span style={{ color: FACTION_COLORS[winner], fontWeight: 700 }}>{winner}</span>
          </div>
        )}

        <Slots slots={slots} gameStatus={gameStatus} gameId={gameId}
          onJoin={onJoin} onAssignAI={onAssignAI} onReleaseAI={onReleaseAI}
          onReady={onReady} onLeave={onLeave} onViewInstruction={onViewInstruction} />
        <BattlePreviewCard data={data || {}} navigate={navigate} />
        <div className="spectate-row">
          <button className="btn-ghost" onClick={() => navigate(`/spectate?game=${data?.game_id}`)}>仅观战(不占槽位)</button>
        </div>

        <Footer today={today} />
      </div>
    </div>
  );
}

// ── Countdown overlay ──────────────────────────────────────────
function CountdownOverlay({ deadline }) {
  const [sec, setSec] = useState(5);
  useEffect(() => {
    if (!deadline) return;
    const tick = () => {
      const remaining = Math.max(0, Math.ceil((new Date(deadline).getTime() - Date.now()) / 1000));
      setSec(remaining);
    };
    tick();
    const timer = setInterval(tick, 200);
    return () => clearInterval(timer);
  }, [deadline]);
  if (sec <= 0) return null;
  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 100,
      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      background: 'rgba(31,26,22,0.75)', backdropFilter: 'blur(6px)',
    }}>
      <div style={{ fontSize: 96, fontWeight: 900, color: '#faf3e2', fontFamily: 'var(--font-sans)', lineHeight: 1 }}>{sec}</div>
      <div style={{ fontSize: 18, color: 'rgba(250,243,226,0.7)', marginTop: 12, letterSpacing: 6 }}>倒计时</div>
    </div>
  );
}

// ── InkHomePage root — full lobby logic ───────────────────────
function InkHomePage() {
  const navigate = useNavigate();
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);

  // Adaptive polling
  const [pollInterval, setPollInterval] = useState(5000);
  const { data, isLoading } = usePolling('/v1/lobby/status', { intervalMs: pollInterval });

  useEffect(() => {
    if (!data?.status) return;
    const next = data.status === 'finished' ? null
      : data.status === 'countdown' ? 1000
      : data.status === 'lobby' ? 5000
      : 3000;
    setPollInterval(prev => prev === next ? prev : next);
  }, [data?.status]);

  // Optimistic updates
  const [localSlots, setLocalSlots] = useState(null);
  const pendingRef = useRef(null);
  const [msg, setMsg] = useState(null);
  const msgTimer = useRef(null);

  // Modal state
  const [modalFaction, setModalFaction] = useState(null);
  const [modalPhase, setModalPhase] = useState(null);
  const [savedResult, setSavedResult] = useState(null);

  const gameId = data?.game_id;
  const gameStatus = data?.status;
  const winner = data?.winner;
  const slots = localSlots || data?.slots;
  const countdownDeadline = data?.countdown_deadline;

  // Resolve optimistic updates
  useEffect(() => {
    const pending = pendingRef.current;
    if (!pending) { setLocalSlots(null); return; }
    const serverSlot = data?.slots?.[pending.faction];
    if (serverSlot && pending.check(serverSlot)) { setLocalSlots(null); pendingRef.current = null; }
    else if (Date.now() > pending.until) { setLocalSlots(null); pendingRef.current = null; }
  }, [data?.slots]);

  function flash(text) { setMsg(text); clearTimeout(msgTimer.current); msgTimer.current = setTimeout(() => setMsg(null), 5000); }
  function _revert(faction) { setLocalSlots(prev => { if (!prev) return prev; const next = { ...prev }; delete next[faction]; return next; }); }

  // ── Write handlers (C2) ────────────────────────────────────
  async function actJoin(faction) {
    flash(null);
    pendingRef.current = { faction, check: s => s.status === 'occupied', until: Date.now() + 5000 };
    setLocalSlots(prev => ({ ...(prev || slots), [faction]: { status: 'occupied', ready: false, agent_display_name: '你', ip: '***' } }));
    try { await api.joinLobby(faction); flash(`已加入 ${faction}`); }
    catch (e) { _revert(faction); pendingRef.current = null; if (e.code === 'COUNTDOWN_STARTED') flash('倒计时已启动，无法加入'); else flash(`加入失败: ${e.message}`); }
  }
  async function actAssignAI(faction) {
    flash(null);
    pendingRef.current = { faction, check: s => s.status === 'ai_managed', until: Date.now() + 5000 };
    setLocalSlots(prev => ({ ...(prev || slots), [faction]: { status: 'ai_managed', ready: true, agent_display_name: `托管AI-${faction}` } }));
    try { await api.assignAI(faction); flash(`已配 ${faction} 为 AI 托管`); }
    catch (e) { _revert(faction); pendingRef.current = null; flash(e.code === 'recruit_window_active' ? `招募期内，还有 ${e.body?.remaining_sec ?? '?'} 秒可配 AI` : `配 AI 失败: ${e.message}`); }
  }
  async function actReleaseAI(faction) {
    flash(null);
    pendingRef.current = { faction, check: s => s.status === 'open', until: Date.now() + 5000 };
    setLocalSlots(prev => ({ ...(prev || slots), [faction]: { status: 'open', ready: false } }));
    try { await api.releaseAI(faction); flash(`已释放 ${faction} AI 托管`); }
    catch (e) { _revert(faction); pendingRef.current = null; flash(`释放失败: ${e.message}`); }
  }
  async function actReady(faction, token) {
    flash(null);
    pendingRef.current = { faction, check: s => s.ready === true, until: Date.now() + 5000 };
    setLocalSlots(prev => ({ ...(prev || slots), [faction]: { ...((prev || slots)[faction]), ready: true } }));
    try { await api.ready(token); flash('已就绪'); }
    catch (e) { _revert(faction); pendingRef.current = null; flash(`Ready 失败: ${e.message}`); }
  }
  async function doLeave(faction, token) {
    try {
      const r = await fetch(`/v1/games/${gameId}/leave?token=${encodeURIComponent(token)}`, { method: 'POST' });
      if (r.status === 401 || r.status === 410) {
        try { const sessions = JSON.parse(localStorage.getItem('arena_sessions') || '{}'); delete sessions[faction]; localStorage.setItem('arena_sessions', JSON.stringify(sessions)); } catch {}
        alert('Token 已失效，页面将刷新'); window.location.reload(); return;
      }
      const d = await r.json();
      if (!r.ok) { flash(d.detail || '退出失败'); return; }
      try { const sessions = JSON.parse(localStorage.getItem('arena_sessions') || '{}'); delete sessions[faction]; localStorage.setItem('arena_sessions', JSON.stringify(sessions)); } catch {}
      if (d.redirect_to) window.location.href = d.redirect_to;
      else flash('已退出');
    } catch { flash('退出请求失败'); }
  }

  return (
    <>
      <InkLandscape opacity={t.bg_opacity} motion={t.bg_motion} layout={t.bg_layout} />
      <InkDragon enabled={t.bg_motion} />

      {/* Flash message */}
      {msg && (
        <div style={{ position: 'fixed', top: 80, left: '50%', transform: 'translateX(-50%)', zIndex: 200,
          background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 8,
          padding: '10px 24px', fontSize: 'var(--fs-body)', boxShadow: '0 4px 24px rgba(0,0,0,0.12)' }}>
          {msg}
        </div>
      )}

      <HomePagePreview
        data={data}
        slots={slots}
        gameId={gameId}
        gameStatus={gameStatus}
        winner={winner}
        countdownDeadline={countdownDeadline}
        heroMode={t.hero_mode}
        isLoading={isLoading}
        onJoin={(f) => { setModalPhase('confirm'); setModalFaction(f); }}
        onAssignAI={actAssignAI}
        onReleaseAI={actReleaseAI}
        onReady={actReady}
        onLeave={doLeave}
        onViewInstruction={(f, saved) => { setModalFaction(f); setModalPhase('done'); setSavedResult(saved); }}
        navigate={navigate}
      />

      {/* Countdown overlay */}
      {gameStatus === 'countdown' && countdownDeadline && <CountdownOverlay deadline={countdownDeadline} />}

      {/* JoinModal */}
      {modalFaction && (
        <JoinModal faction={modalFaction} gameId={gameId}
          gameStatus={gameStatus}
          slotReady={slots?.[modalFaction]?.ready}
          onClose={() => { setModalFaction(null); setModalPhase(null); setSavedResult(null); }}
          initialPhase={modalPhase || 'confirm'}
          preResult={savedResult}
          onLeave={(d) => { setModalFaction(null); setModalPhase(null); setSavedResult(null); if (d.redirect_to) window.location.href = d.redirect_to; }} />
      )}

      <TweaksPanel title="Tweaks">
        <TweakSection title="水墨背景">
          <TweakRadio label="布局" value={t.bg_layout}
            onChange={(v) => setTweak("bg_layout", v)}
            options={[
              { value: "scroll", label: "中轴" },
              { value: "mirror", label: "镜像" },
              { value: "fill",   label: "满幅" },
            ]} />
          <TweakSlider label="透明度" value={t.bg_opacity}
            min={0} max={1} step={0.05}
            onChange={(v) => setTweak("bg_opacity", v)} />
          <TweakToggle label="动画交互"
            value={t.bg_motion}
            onChange={(v) => setTweak("bg_motion", v)} />
        </TweakSection>
        <TweakSection title="演武图">
          <TweakSelect label="数据源" value={t.hero_mode}
            onChange={(v) => setTweak("hero_mode", v)}
            options={[
              { value: "auto",   label: "auto · 自动选择" },
              { value: "live",   label: "live · 实时对局" },
              { value: "replay", label: "replay · 最近一场回放" },
              { value: "demo",   label: "demo · 纯演示" },
            ]} />
        </TweakSection>
        <TweakSection title="大厅状态">
          <TweakSelect label="对局阶段" value={t.lobby_state}
            onChange={(v) => setTweak("lobby_state", v)}
            options={[
              { value: "fresh", label: "全空缺(刚开新局)" },
              { value: "mixed", label: "混合(2 玩家 + 1 AI)" },
              { value: "countdown", label: "倒计时即将开打" },
              { value: "active", label: "对局进行中" },
            ]} />
          <TweakSelect label="本地 session" value={t.saved_session}
            onChange={(v) => setTweak("saved_session", v)}
            options={[
              { value: "none", label: "无" },
              { value: "蜀", label: "已加入 蜀" },
              { value: "魏", label: "已加入 魏" },
              { value: "吴", label: "已加入 吴" },
            ]} />
        </TweakSection>
      </TweaksPanel>
    </>
  );
}

export default InkHomePage;
