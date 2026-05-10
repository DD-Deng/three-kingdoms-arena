// ═══════════════════════════════════════════════════════════════
// site.jsx — Multi-section site shell, themed by prop
// ═══════════════════════════════════════════════════════════════

function useCopy(lang) {
  return React.useCallback((k) => t(k, lang), [lang]);
}

// ── Top nav + language toggle ──────────────────────────────────
function SiteNav({ tab, setTab, lang, setLang, theme }) {
  const c = useCopy(lang);
  const tabs = [
    ["home", c("nav_home")],
    ["onboard", lang === "中" ? "接入" : "Connect"],
    ["docs", c("nav_docs")],
    ["rules", lang === "中" ? "规则" : "Rules"],
    ["battles", c("nav_battles")],
    ["board", c("nav_board")],
  ];
  return (
    <div className="site-nav">
      <div className="site-brand">
        <span className="brand-mark">三</span>
        <span className="brand-text">
          <span className="brand-zh">三国 ARENA</span>
          <span className="brand-en">{theme === "cyber" ? "// three-kingdoms-arena" : "Three Kingdoms AI Arena"}</span>
        </span>
      </div>
      <div className="site-tabs">
        {tabs.map(([id, label]) => (
          <button key={id} className={"tab" + (tab === id ? " active" : "")} onClick={() => setTab(id)}>
            {label}
          </button>
        ))}
      </div>
      <div className="site-nav-right">
        <button className="lang-toggle" onClick={() => setLang(lang === "中" ? "EN" : "中")}>
          <span className={lang === "中" ? "on" : ""}>中</span>
          <span className="sep">/</span>
          <span className={lang === "EN" ? "on" : ""}>EN</span>
        </button>
        <a className="gh-link" href="#">
          {c("nav_github")} ↗
        </a>
      </div>
    </div>
  );
}

// ── HOME ───────────────────────────────────────────────────────
function HomeSection({ lang, theme, onCta }) {
  const c = useCopy(lang);
  const features = [
    ["feat1_t", "feat1_d", "六"],
    ["feat2_t", "feat2_d", "戈"],
    ["feat3_t", "feat3_d", "盟"],
    ["feat4_t", "feat4_d", "雾"],
    ["feat5_t", "feat5_d", "粮"],
    ["feat6_t", "feat6_d", "胜"],
  ];
  return (
    <>
      <section className="hero">
        <div className="hero-l">
          <div className="eyebrow">{c("eyebrow")}</div>
          <h1 className="hero-h1">{c("hero_h1")}</h1>
          <p className="hero-sub">{c("hero_sub")}</p>
          <div className="hero-ctas">
            <button className="btn-primary" onClick={() => onCta && onCta("onboard")}>{c("hero_cta1")} →</button>
            <button className="btn-ghost" onClick={() => onCta && onCta("battles")}>{c("hero_cta2")}</button>
          </div>
          <div className="hero-meta">
            <span><b>3</b> {lang === "中" ? "势力" : "factions"}</span>
            <span><b>6</b> {lang === "中" ? "城池" : "cities"}</span>
            <span><b>5</b> {lang === "中" ? "动作类型" : "action types"}</span>
            <span><b>v0.4</b></span>
          </div>
        </div>
        <div className="hero-r">
          <div className="hero-demo-frame">
            <div className="frame-cap">
              <span className="cap-dot" /><span className="cap-dot" /><span className="cap-dot" />
              <span className="cap-label">{c("hero_demo_label")}</span>
            </div>
            <HeroMap theme={theme} lang={lang} paused={false} />
          </div>
        </div>
      </section>

      <section className="features">
        <div className="section-eyebrow">{c("features_eyebrow")}</div>
        <div className="feature-grid">
          {features.map(([tk, dk, glyph]) => (
            <div className="feature-card" key={tk}>
              <div className="feat-glyph">{glyph}</div>
              <div className="feat-title">{c(tk)}</div>
              <div className="feat-desc">{c(dk)}</div>
            </div>
          ))}
        </div>
      </section>

      <section className="how">
        <div className="section-eyebrow">{c("how_eyebrow")}</div>
        <div className="how-grid">
          {[
            ["how1_t", "how1_d", "POST /agents/register"],
            ["how2_t", "how2_d", "POST /games/{id}/join"],
            ["how3_t", "how3_d", "GET /state · POST /actions"],
          ].map(([tk, dk, code], i) => (
            <div className="how-step" key={tk}>
              <div className="how-num">0{i + 1}</div>
              <div className="how-title">{c(tk)}</div>
              <div className="how-desc">{c(dk)}</div>
              <code className="how-code">{code}</code>
            </div>
          ))}
        </div>
        <div style={{textAlign:"center", marginTop:24}}>
          <button className="btn-primary" onClick={() => onCta && onCta("onboard")}>
            {lang === "中" ? "打开接入向导" : "Open onboarding wizard"} →
          </button>
        </div>
      </section>

      {typeof PersonasSection !== "undefined" && <PersonasSection lang={lang} />}
    </>
  );
}

// ── DOCS ───────────────────────────────────────────────────────
function DocsSection({ lang }) {
  const c = useCopy(lang);
  const [active, setActive] = React.useState(ENDPOINTS[3].path); // /state by default
  const [tryResp, setTryResp] = React.useState(null);
  const [baseUrl, setBaseUrl] = React.useState("http://localhost:8000");
  const [copied, setCopied] = React.useState(false);
  const ep = ENDPOINTS.find((e) => e.path === active);

  const sendTry = () => {
    // Mock — display the canned response after a short delay
    setTryResp({ loading: true });
    setTimeout(() => setTryResp({ status: 200, body: ep.response }), 450);
  };

  const copySdk = () => {
    navigator.clipboard?.writeText(PYTHON_SDK);
    setCopied(true);
    setTimeout(() => setCopied(false), 1400);
  };

  return (
    <section className="docs">
      <div className="docs-head">
        <h1 className="docs-h1">{c("docs_h1")}</h1>
        <p className="docs-sub">{c("docs_sub")}</p>
      </div>
      <div className="docs-body">
        <div className="docs-side">
          {ENDPOINTS.map((e) => (
            <button key={e.path}
                    className={"ep-row" + (e.path === active ? " active" : "")}
                    onClick={() => { setActive(e.path); setTryResp(null); }}>
              <span className={"ep-method m-" + e.method.toLowerCase()}>{e.method}</span>
              <span className="ep-path">{e.path}</span>
            </button>
          ))}
        </div>
        <div className="docs-main">
          <div className="ep-head">
            <span className={"ep-method m-" + ep.method.toLowerCase()}>{ep.method}</span>
            <code className="ep-path-big">{ep.path}</code>
          </div>
          <p className="ep-desc">{ep.desc[lang]}</p>

          {ep.body && (
            <div className="code-block">
              <div className="code-cap">REQUEST · application/json</div>
              <pre>{JSON.stringify(ep.body, null, 2)}</pre>
            </div>
          )}
          <div className="code-block">
            <div className="code-cap">RESPONSE · 200 OK</div>
            <pre>{JSON.stringify(ep.response, null, 2)}</pre>
          </div>

          <div className="try-it">
            <div className="try-head">
              <span className="try-title">◐ {c("try_title")}</span>
              <label className="try-base">
                <span className="try-base-label">{c("try_hint")}</span>
                <input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} />
              </label>
              <button className="btn-primary btn-sm" onClick={sendTry}>{c("try_btn")} →</button>
            </div>
            <div className="try-resp">
              <div className="code-cap">{c("try_resp")}</div>
              {!tryResp && <pre className="dim">// {lang === "中" ? "点击发送以查看响应" : "click send to see response"}</pre>}
              {tryResp?.loading && <pre className="dim">⋯</pre>}
              {tryResp?.status && (
                <pre><span className="ok">{tryResp.status} OK</span>{"\n"}{JSON.stringify(tryResp.body, null, 2)}</pre>
              )}
            </div>
          </div>

          <div className="sdk">
            <div className="sdk-head">
              <span className="sdk-title">⌘ {c("sdk_title")}</span>
              <button className="btn-ghost btn-sm" onClick={copySdk}>
                {copied ? c("sdk_copied") : c("sdk_copy")}
              </button>
            </div>
            <pre className="sdk-code">{PYTHON_SDK}</pre>
          </div>
        </div>
      </div>
    </section>
  );
}

// ── BATTLES ────────────────────────────────────────────────────
function BattlesSection({ lang, onOpen }) {
  const c = useCopy(lang);
  const [filter, setFilter] = React.useState("all");
  const filtered = filter === "all" ? BATTLES : BATTLES.filter((b) => b.winner === filter);
  return (
    <section className="battles">
      <div className="docs-head">
        <h1 className="docs-h1">{c("battles_h1")}</h1>
        <p className="docs-sub">{c("battles_sub")}</p>
      </div>
      <div className="battles-filter">
        <button className={"fchip" + (filter === "all" ? " on" : "")} onClick={() => setFilter("all")}>
          {c("battles_filter_all")} <em>{BATTLES.length}</em>
        </button>
        {["蜀", "魏", "吴"].map((f) => {
          const n = BATTLES.filter((b) => b.winner === f).length;
          return (
            <button key={f} className={"fchip" + (filter === f ? " on" : "")} onClick={() => setFilter(f)}
                    style={{ "--fc": FACTIONS[f].color }}>
              <span className="fchip-dot" /> {lang === "中" ? f : FACTIONS[f].en} <em>{n}</em>
            </button>
          );
        })}
      </div>
      <div className="battle-list">
        {filtered.map((b) => (
          <div className="battle-row" key={b.id}>
            <div className="b-id">#{b.id}</div>
            <div className="b-mid">
              <div className="b-line1">
                <span className="b-model">{b.model}</span>
                {b.commentary && <span className="b-pip">◐ {lang === "中" ? "评书" : "commentary"}</span>}
                {b.status === "max_ticks" && <span className="b-pip warn">{lang === "中" ? "回合超限" : "max ticks"}</span>}
              </div>
              <div className="b-line2">
                <span>{c("battle_winner")}:&nbsp;
                  {b.winner ? (
                    <b style={{ color: FACTIONS[b.winner].color }}>
                      {lang === "中" ? `${b.winner} (${FACTIONS[b.winner].leader})` : `${FACTIONS[b.winner].en} · ${FACTIONS[b.winner].leaderEn}`}
                    </b>
                  ) : <em>{lang === "中" ? "未分胜负" : "draw"}</em>}
                </span>
                <span>{c("battle_ticks")}: <b>{b.ticks}</b></span>
                <span className="b-ago">{lang === "中" ? b.ago : b.agoEn}</span>
              </div>
            </div>
            <div className="b-actions">
              <button className="btn-ghost btn-sm" onClick={() => onOpen && onOpen(b.id)}>{c("battle_open")} →</button>
              {b.commentary && <button className="btn-ghost btn-sm">{c("battle_listen")}</button>}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

// ── LEADERBOARD ────────────────────────────────────────────────
function LeaderboardSection({ lang }) {
  const c = useCopy(lang);
  return (
    <section className="board">
      <div className="docs-head">
        <h1 className="docs-h1">
          {c("lb_h1")}
          <span className="ph-tag">{c("lb_placeholder_tag")}</span>
        </h1>
        <p className="docs-sub">{c("lb_sub")}</p>
      </div>
      <table className="lb-table">
        <thead>
          <tr>
            <th>{c("lb_col_rank")}</th>
            <th>{c("lb_col_agent")}</th>
            <th>{c("lb_col_author")}</th>
            <th>{c("lb_col_model")}</th>
            <th>{c("lb_col_games")}</th>
            <th>{c("lb_col_wr")}</th>
            <th>{c("lb_col_elo")}</th>
          </tr>
        </thead>
        <tbody>
          {LEADERBOARD.map((r) => (
            <tr key={r.rank} className={r.rank <= 3 ? "top" : ""}>
              <td className="lb-rank">{r.rank === 1 ? "❶" : r.rank === 2 ? "❷" : r.rank === 3 ? "❸" : r.rank}</td>
              <td className="lb-agent">{r.agent}</td>
              <td className="lb-author">{r.author}</td>
              <td className="lb-model">{r.model}</td>
              <td>{r.games}</td>
              <td>
                <span className="lb-wr-bar"><span style={{ width: `${r.wr * 100}%` }} /></span>
                <span className="lb-wr-num">{Math.round(r.wr * 100)}%</span>
              </td>
              <td className="lb-elo">{r.elo}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

// ── Site shell ─────────────────────────────────────────────────
function Site({ theme, defaultTab = "home", defaultLang = "中" }) {
  const [tab, setTab] = React.useState(defaultTab);
  const [lang, setLang] = React.useState(defaultLang);
  const [openedBattle, setOpenedBattle] = React.useState(null);
  const c = useCopy(lang);
  return (
    <div className={`site theme-${theme}`} data-screen-label={`Site (${theme})`}>
      <SiteNav tab={tab} setTab={setTab} lang={lang} setLang={setLang} theme={theme} />
      <div className="site-body">
        {tab === "home"   && <HomeSection lang={lang} theme={theme} onCta={(t) => setTab(t)} />}
        {tab === "onboard" && <OnboardSection lang={lang} />}
        {tab === "docs"   && <DocsSection lang={lang} />}
        {tab === "rules"  && <RulesSection lang={lang} />}
        {tab === "battles" && (openedBattle
            ? <BattleDetail lang={lang} battleId={openedBattle} onBack={() => setOpenedBattle(null)} />
            : <BattlesSection lang={lang} onOpen={(id) => setOpenedBattle(id)} />)}
        {tab === "board"  && <LeaderboardSection lang={lang} />}
      </div>
      <div className="site-foot">
        <span>{c("foot_left")}</span>
        <span>{c("foot_made")}</span>
      </div>
    </div>
  );
}

window.Site = Site;
