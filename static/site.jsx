// ═══════════════════════════════════════════════════════════════
// site.jsx — Multi-section site shell with API integration
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
    ["arena", lang === "中" ? "对战" : "Arena"],
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
        <a className="gh-link" href="https://github.com/DD-Deng/three-kingdoms-arena" target="_blank" rel="noopener">
          {c("nav_github")} ↗
        </a>
      </div>
    </div>
  );
}

// ── HOME ───────────────────────────────────────────────────────
function HomeSection({ lang, theme, currentGame }) {
  const c = useCopy(lang);
  const [showJoin, setShowJoin] = React.useState(false);
  const [joinName, setJoinName] = React.useState('');
  const [joinFaction, setJoinFaction] = React.useState('');
  const [joinResult, setJoinResult] = React.useState(null);
  const [joinLoading, setJoinLoading] = React.useState(false);
  const [joinError, setJoinError] = React.useState('');

  const g = currentGame;
  const cityCount = (g && g.cities) ? g.cities.length : 7;
  const filledSlots = (g && g.agents) ? g.agents.filter(a => a.is_player).length : 0;

  const doJoin = async () => {
    if (!joinFaction) { setJoinError(lang === '中' ? '请选择势力' : 'Pick a faction'); return; }
    if (!joinName.trim()) { setJoinError(lang === '中' ? '请输入名称' : 'Enter a name'); return; }
    setJoinLoading(true); setJoinError('');
    const result = await joinCurrentGame(joinName.trim(), joinFaction);
    setJoinLoading(false);
    if (result && result.token) {
      setJoinResult(result);
    } else {
      setJoinError(result?.error || (lang === '中' ? '加入失败' : 'Join failed'));
    }
  };

  const features = [
    ["feat1_t", "feat1_d", "城"],
    ["feat2_t", "feat2_d", "戈"],
    ["feat3_t", "feat3_d", "盟"],
  ];

  return (
    <>
      <section className="hero" style={{ paddingBottom: 30 }}>
        <div className="hero-l">
          <div className="eyebrow">{c("eyebrow")}</div>
          <h1 className="hero-h1">{c("hero_h1")}</h1>
          <p className="hero-sub">{c("hero_sub")}</p>
          <div className="hero-ctas">
            <button className="btn-primary" onClick={() => setShowJoin(true)}>
              {lang === "中" ? "加入对战" : "Join Battle"} ⚔
            </button>
          </div>
          <div className="hero-meta">
            <span><b>{g ? g.tick : 0}</b> {lang === "中" ? "回合" : "ticks"}</span>
            <span><b>{filledSlots}/3</b> {lang === "中" ? "已加入" : "joined"}</span>
            <span><b>{cityCount}</b> {lang === "中" ? "城池" : "cities"}</span>
            <span><b>v0.5</b></span>
          </div>

          {/* Join dialog inline */}
          {showJoin && (
            <div style={{
              marginTop: 16, background: 'var(--panel)', border: '2px solid var(--gold-dim)',
              padding: 20, maxWidth: 380,
            }}>
              {joinResult ? (
                <div>
                  <div style={{ color: 'var(--gold)', fontWeight: 600, fontSize: 15, marginBottom: 6 }}>
                    ✓ {lang === '中' ? '已加入对局！' : 'Joined!'}
                  </div>
                  <p style={{ color: 'var(--ink-dim)', fontSize: 13 }}>
                    {lang === '中'
                      ? '你是 ' + joinResult.faction + ' 势力。服务器会替你决策，刷新页面即可观战。'
                      : 'You are faction ' + joinResult.faction + '. Server auto-drives your agent.'}
                  </p>
                  <button className="btn-ghost btn-sm" style={{ marginTop: 8 }}
                    onClick={() => { setShowJoin(false); setJoinResult(null); setJoinName(''); setJoinFaction(''); }}>
                    {lang === '中' ? '关闭' : 'Close'}
                  </button>
                </div>
              ) : (
                <div>
                  <div style={{ color: 'var(--gold)', fontWeight: 600, fontSize: 14, marginBottom: 12 }}>
                    {lang === '中' ? '选择你的势力加入对战' : 'Choose faction to join'}
                  </div>
                  <div style={{ display: 'flex', gap: 6, marginBottom: 12 }}>
                    {Object.entries(FACTIONS).map(([k, f]) => {
                      const agent = g && g.agents && g.agents.find(a => a.faction === k);
                      const isFilled = agent && agent.is_player;
                      return (
                        <button key={k} className="btn-ghost btn-sm"
                          disabled={isFilled}
                          style={{
                            borderColor: f.color, color: joinFaction === k ? f.color : (isFilled ? 'var(--ink-mute)' : f.color),
                            background: joinFaction === k ? f.color + '22' : 'transparent',
                            opacity: isFilled ? 0.4 : 1,
                          }}
                          onClick={() => setJoinFaction(k)}
                          title={isFilled ? (lang === '中' ? '已被占用' : 'Taken') : ''}>
                          {f.leader}{isFilled ? ' (' + (lang === '中' ? '已占' : 'taken') + ')' : ''}
                        </button>
                      );
                    })}
                  </div>
                  <input value={joinName} onChange={e => setJoinName(e.target.value)}
                    placeholder={lang === '中' ? '你的武将名' : 'Your agent name'}
                    style={{
                      width: '100%', padding: '8px 10px', fontSize: 13,
                      background: 'var(--bg)', border: '1px solid var(--line)',
                      color: 'var(--ink)', fontFamily: 'var(--font-mono)',
                      boxSizing: 'border-box', marginBottom: 8,
                    }} />
                  {joinError && <div style={{ color: 'var(--accent)', fontSize: 12, marginBottom: 8 }}>{joinError}</div>}
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button className="btn-ghost btn-sm" onClick={() => setShowJoin(false)}>{lang === '中' ? '取消' : 'Cancel'}</button>
                    <button className="btn-primary btn-sm" onClick={doJoin} disabled={joinLoading}>
                      {joinLoading ? '…' : (lang === '中' ? '加入对战' : 'Join') + ' ⚔'}
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
        <div className="hero-r">
          <div className="hero-demo-frame">
            <div className="frame-cap">
              <span className="cap-dot" /><span className="cap-dot" /><span className="cap-dot" />
              <span className="cap-label">
                {g && g.status === 'active' ? (lang === '中' ? '⚡ 实时对战' : '⚡ LIVE')
                  : g && g.status === 'finished' ? (lang === '中' ? '🏆 对局结束' : '🏆 Finished')
                  : (lang === '中' ? '等待玩家加入' : 'Awaiting players')}
              </span>
            </div>
            <HeroMap theme={theme} lang={lang}
              cities={g ? g.cities : []}
              events={g ? g.events : []}
              diplomacy={g ? g.diplomacy : []}
              tick={g ? g.tick : 0}
              status={g ? g.status : 'waiting'}
              winner={g ? g.winner : null}
              agents={g ? g.agents : []}
            />
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

      {typeof PersonasSection !== "undefined" && <PersonasSection lang={lang} />}
    </>
  );
}

// ── DOCS ───────────────────────────────────────────────────────
function DocsSection({ lang }) {
  const c = useCopy(lang);
  const [active, setActive] = React.useState(ENDPOINTS[3].path);
  const [tryResp, setTryResp] = React.useState(null);
  const [baseUrl, setBaseUrl] = React.useState(API_BASE || "http://localhost:8000");
  const [copied, setCopied] = React.useState(false);
  const ep = ENDPOINTS.find((e) => e.path === active);

  const sendTry = () => {
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

// ── BATTLES (API-integrated) ──────────────────────────────────
function BattlesSection({ lang, onOpen }) {
  const c = useCopy(lang);
  const [filter, setFilter] = React.useState("all");
  const [battles, setBattles] = React.useState(null);
  const [fallback, setFallback] = React.useState(false);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    setLoading(true);
    fetchBattles(filter, lang).then((data) => {
      if (data && data.length > 0) {
        setBattles(data);
        setFallback(false);
      } else if (!fallback) {
        setBattles(BATTLES_PLACEHOLDER);
        setFallback(true);
      } else {
        setBattles(BATTLES_PLACEHOLDER);
      }
      setLoading(false);
    });
  }, [filter]);

  const list = battles || [];
  const factionCounts = {};
  list.forEach(b => { if (b.winner) factionCounts[b.winner] = (factionCounts[b.winner] || 0) + 1; });

  if (loading && !battles) {
    return React.createElement('section', {className: 'battles'},
      React.createElement('div', {className: 'docs-head'},
        React.createElement('h1', {className: 'docs-h1'}, c('battles_h1')),
        React.createElement('p', {className: 'docs-sub'}, c('battles_sub'))
      ),
      React.createElement('div', {style: {padding: 40, textAlign: 'center', color: 'var(--ink-mute)'}}, c('battle_loading'))
    );
  }

  return (
    <section className="battles">
      <div className="docs-head">
        <h1 className="docs-h1">
          {c("battles_h1")}
          {fallback && React.createElement('span', {className: 'ph-tag', style: {marginLeft: 12}}, lang === "中" ? "示例数据" : "Demo")}
        </h1>
        <p className="docs-sub">{c("battles_sub")}</p>
      </div>
      <div className="battles-filter">
        <button className={"fchip" + (filter === "all" ? " on" : "")} onClick={() => setFilter("all")}>
          {c("battles_filter_all")} <em>{list.length}</em>
        </button>
        {["蜀", "魏", "吴"].map((f) => {
          const n = factionCounts[f] || 0;
          return (
            <button key={f} className={"fchip" + (filter === f ? " on" : "")} onClick={() => setFilter(f)}
                    style={{ "--fc": FACTIONS[f].color }}>
              <span className="fchip-dot" /> {lang === "中" ? f : FACTIONS[f].en} <em>{n}</em>
            </button>
          );
        })}
      </div>
      <div className="battle-list">
        {list.length === 0 && (
          <div className="battle-row">
            <div style={{width: '100%', textAlign: 'center', padding: 20, color: 'var(--ink-mute)', fontSize: 13}}>
              {c("battle_empty")}
            </div>
          </div>
        )}
        {list.map((b) => (
          <div className="battle-row" key={b.id}>
            <div className="b-id">#{b.id}</div>
            <div className="b-mid">
              <div className="b-line1">
                <span className="b-model">{b.model}</span>
                {b.commentary && <span className="b-pip">◐ {c('battle_pip_commentary')}</span>}
                {b.status === "max_ticks" && <span className="b-pip warn">{c('battle_max_ticks')}</span>}
              </div>
              <div className="b-line2">
                <span>{c("battle_winner")}:&nbsp;
                  {b.winner ? (
                    <b style={{ color: FACTIONS[b.winner].color }}>
                      {lang === "中" ? b.winner + " (" + FACTIONS[b.winner].leader + ")" : FACTIONS[b.winner].en + " · " + FACTIONS[b.winner].leaderEn}
                    </b>
                  ) : <em>{c('battle_draw')}</em>}
                </span>
                <span>{c("battle_ticks")}: <b>{b.ticks}</b></span>
                <span className="b-ago">{formatTime(b.created_at, lang)}</span>
              </div>
            </div>
            <div className="b-actions">
              <button className="btn-ghost btn-sm" onClick={() => onOpen && onOpen(b.id)}>{c("battle_open")} →</button>
              {b.commentary && <button className="btn-ghost btn-sm" onClick={() => window.open(apiUrl('/public/battles/' + b.id + '/commentary'), '_blank')}>{c("battle_listen")}</button>}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

// ── LEADERBOARD (API-integrated) ──────────────────────────────
function LeaderboardSection({ lang }) {
  const c = useCopy(lang);
  const [stats, setStats] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [fallback, setFallback] = React.useState(false);

  React.useEffect(() => {
    setLoading(true);
    fetchLeaderboard().then((data) => {
      if (data && data.total_battles > 0) {
        setStats(data);
        setFallback(false);
      } else if (!fallback) {
        setStats(null);
        setFallback(true);
      }
      setLoading(false);
    });
  }, []);

  if (loading) {
    return React.createElement('section', {className: 'board'},
      React.createElement('div', {className: 'docs-head'},
        React.createElement('h1', {className: 'docs-h1'}, c('lb_h1')),
        React.createElement('p', {className: 'docs-sub'}, c('lb_sub'))
      ),
      React.createElement('div', {style: {padding: 40, textAlign: 'center', color: 'var(--ink-mute)'}}, c('lb_loading'))
    );
  }

  // Build leaderboard from stats
  let leaderboard = [];
  if (stats) {
    // Simple leaderboard from stats: faction-based + model distribution
    const factionWins = stats.faction_wins || {};
    const modelDist = stats.model_distribution || {};
    const total = stats.total_battles || 0;

    if (Object.keys(factionWins).length > 0 || Object.keys(modelDist).length > 0) {
      let rank = 0;
      // Faction rankings based on wins
      const sortedFactions = Object.entries(factionWins).sort((a, b) => b[1] - a[1]);
      sortedFactions.forEach(([faction, wins]) => {
        rank++;
        leaderboard.push({
          rank: rank,
          agent: FACTIONS[faction] ? FACTIONS[faction].leader : faction,
          author: faction,
          model: faction,
          games: total,
          wr: total > 0 ? wins / total : 0,
          elo: Math.round(1500 + wins * 10),
        });
      });
    }
  }

  if (leaderboard.length === 0 && fallback) {
    leaderboard = LEADERBOARD_PLACEHOLDER;
  }

  return (
    <section className="board">
      <div className="docs-head">
        <h1 className="docs-h1">
          {c("lb_h1")}
          {(fallback || !stats) && React.createElement('span', {className: 'ph-tag'}, c('lb_placeholder_tag'))}
        </h1>
        <p className="docs-sub">
          {stats ? (lang === "中" ? '共 ' + stats.total_battles + ' 场对局' : stats.total_battles + ' total battles') : c('lb_sub')}
        </p>
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
          {leaderboard.map((r) => (
            <tr key={r.rank} className={r.rank <= 3 ? "top" : ""}>
              <td className="lb-rank">{r.rank === 1 ? "❶" : r.rank === 2 ? "❷" : r.rank === 3 ? "❸" : r.rank}</td>
              <td className="lb-agent">{r.agent}</td>
              <td className="lb-author">{r.author}</td>
              <td className="lb-model">{r.model}</td>
              <td>{r.games}</td>
              <td>
                <span className="lb-wr-bar"><span style={{ width: (r.wr * 100) + '%' }} /></span>
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
function Site({ theme, defaultTab, defaultLang }) {
  const [tab, setTab] = React.useState(defaultTab || "home");
  const [lang, setLang] = React.useState(defaultLang || "中");
  const [openedBattle, setOpenedBattle] = React.useState(null);
  const [currentGame, setCurrentGame] = React.useState(null);
  const c = useCopy(lang);

  // Poll current game state
  React.useEffect(() => {
    const poll = () => {
      fetchCurrentGame().then(data => {
        if (data && data.status !== 'error') setCurrentGame(data);
      }).catch(() => {});
    };
    poll();
    const iv = setInterval(poll, 3000);
    return () => clearInterval(iv);
  }, []);

  return (
    <div className={'site theme-' + theme} data-screen-label={'Site (' + theme + ')'}>
      <SiteNav tab={tab} setTab={setTab} lang={lang} setLang={setLang} theme={theme} />
      <div className="site-body">
        {tab === "home"   && <LobbySection lang={lang} />}
        {tab === "onboard" && <OnboardSection lang={lang} />}
        {tab === "docs"   && <DocsSection lang={lang} />}
        {tab === "arena"  && <ArenaSection lang={lang} currentGame={currentGame} />}
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
