// InkHome — ink-wash homepage preview
import './InkHome.css';
import './InkLandscape.css';
import './InkDragon.css';
import { FACTIONS, F_INFO, LOBBY_PRESETS } from './data';
import { HeroBattle } from './HeroBattle';
import { InkLandscape } from './InkLandscape';
import { InkDragon } from './InkDragon';
import { useTweaks, TweaksPanel, TweakSection, TweakSlider, TweakToggle, TweakRadio, TweakSelect } from './TweaksPanel';

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


// ── Helper for slot UI ────────────────────────────────────────
function slotUI(slot, faction, gameStatus) {
  const s = slot?.status || "open";
  const ready = slot?.ready;
  if (gameStatus === "countdown" || gameStatus === "active") {
    return {
      label: gameStatus === "countdown" ? "倒计时中" : "对局中",
      cssClass: "locked",
      description: `${F_INFO[faction].monarch} · ${slot?.agent_display_name || "—"}`,
      actions: null,
    };
  }
  if (gameStatus === "finished") {
    return { label: "已结束", cssClass: "locked", description: "", actions: null };
  }
  switch (s) {
    case "open": return {
      label: "空缺", cssClass: "open",
      description: `等待玩家或 AI 接入 · ${F_INFO[faction].monarch}`,
      actions: [{ id: "ai", label: "配 AI 托管", kind: "ghost" },
                { id: "join", label: `加入 ${faction}`, kind: "primary" }],
    };
    case "ai_managed": return {
      label: "AI 托管", cssClass: "ai",
      description: slot.agent_display_name || "Managed AI",
      actions: [{ id: "grab", label: `抢占 ${faction}`, kind: "primary" },
                { id: "release", label: "释放 AI", kind: "ghost" }],
    };
    case "occupied": return ready ? {
      label: "已就绪", cssClass: "ready",
      description: `${slot.agent_display_name} · IP ${slot.ip || "***"}`,
      actions: null,
    } : {
      label: "未就绪", cssClass: "occupied",
      description: `${slot.agent_display_name} · 等待 ready`,
      actions: null,
    };
    default: return { label: s, cssClass: "open", description: "", actions: null };
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

// ── Nav ───────────────────────────────────────────────────────
function Nav() {
  const tabs = [
    ["/", "首页"],
    ["/access", "接入"],
    ["/api-docs", "接入文档"],
    ["/rules", "规则"],
    ["/battles", "战报"],
    ["/rankings", "排行榜"],
  ];
  return (
    <nav className="nav">
      <a className="nav-brand" href="#">
        <span className="nav-seal">三</span>
        <span className="nav-brand-text">
          <span className="nav-zh">三国 ARENA</span>
          <span className="nav-en">THREE KINGDOMS ARENA</span>
        </span>
      </a>
      <div className="nav-tabs">
        {tabs.map(([href, label], i) => (
          <a key={href} href={href} className={"nav-tab" + (i === 0 ? " active" : "")}>{label}</a>
        ))}
      </div>
      <div className="nav-right">
        <span className="lang-tog"><span className="on">中</span><span>/</span><span>EN</span></span>
        <a className="gh-link" href="https://github.com/DD-Deng/three-kingdoms-arena">GitHub ↗</a>
      </div>
    </nav>
  );
}

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
  const badgeMap = {
    lobby:     { label: "等待中", cls: "b-lobby" },
    countdown: { label: "倒计时", cls: "b-countdown" },
    active:    { label: "进行中", cls: "b-active" },
    paused:    { label: "已暂停", cls: "b-paused" },
    finished:  { label: "已结束", cls: "b-finished" },
  };
  const b = badgeMap[data.status] || { label: data.status, cls: "b-finished" };
  return (
    <div className="status-row">
      <span className="key">Game</span>
      <span className="val">#{data.game_id}</span>
      <span className="status-sep">·</span>
      <span className="key">Tick</span>
      <span className="val">{data.tick}/{data.max_ticks}</span>
      <span className="status-sep">·</span>
      <span className={"status-badge " + b.cls}>{b.label}</span>
      {data.spectators > 0 && (
        <>
          <span className="status-sep">·</span>
          <span className="key">{data.spectators} 观战</span>
        </>
      )}
    </div>
  );
}

// ── Slots ─────────────────────────────────────────────────────
function Slots({ data, savedSession }) {
  return (
    <div className="slots">
      {FACTIONS.map((f) => {
        const slot = data.slots[f];
        const ui = slotUI(slot, f, data.status);
        const info = F_INFO[f];
        const hasSession = savedSession === f;
        return (
          <div key={f} className="slot" style={{ "--fc": info.color }}>
            {hasSession && (
              <div className="slot-banner">
                <span className="ok">✓</span>
                <span>已加入 {f} 阵营</span>
                <span style={{ color: "var(--ink-mute)", fontSize: 10 }}>· Token 余 27 分钟</span>
                <button className="slot-banner-btn">📋 查看接入指令</button>
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
                          style={a.kind === "primary" ? { "--fc": info.color } : {}}>
                    {a.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Battle preview / spectate CTA ────────────────────────────
function BattlePreviewCard({ data }) {
  if (data.status !== "active") {
    return (
      <div className="preview-card">
        <div className="preview-title">战场态势</div>
        <div className="preview-empty">等待对局开始…</div>
      </div>
    );
  }
  return (
    <div className="preview-card">
      <div className="preview-title">战场态势</div>
      <div className="preview-meta">
        Game #{data.game_id} · Tick {data.tick}/{data.max_ticks} · 成都:蜀 1240兵 · 洛阳:魏 980兵 · 建业:吴 1100兵 · 宛城:中立 ~600
      </div>
      <button className="btn-primary">进入观战页 →</button>
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
function HomePagePreview({ lobbyState, savedSession, heroMode }) {
  const data = LOBBY_PRESETS[lobbyState] || LOBBY_PRESETS.mixed;
  const today = "丙午年 · 仲夏 · 兰纳署";

  return (
    <div className="ink-home">
      <Nav />
      <div className="page">
        <span className="v-mark" style={{ "--top": "60px" }}>群 雄 之 章</span>

        <Hero />

        <BattleStage heroMode={heroMode} />

        <StatusRow data={data} />
        <Slots data={data} savedSession={savedSession} />
        <BattlePreviewCard data={data} />
        <div className="spectate-row">
          <button className="btn-ghost">仅观战(不占槽位)</button>
        </div>

        <Footer today={today} />
      </div>
    </div>
  );
}

// ── InkHomePage root — replicates original homepage.html App ──
function InkHomePage() {
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);

  return (
    <>
      <InkLandscape opacity={t.bg_opacity} motion={t.bg_motion} layout={t.bg_layout} />
      <InkDragon enabled={t.bg_motion} />
      <HomePagePreview
        lobbyState={t.lobby_state}
        savedSession={t.saved_session === "none" ? null : t.saved_session}
        heroMode={t.hero_mode}
      />
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
