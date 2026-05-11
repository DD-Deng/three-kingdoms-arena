// ── Arena Lobby & Room ──────────────────────────────────────
function ArenaSection({ lang }) {
  const c = React.useCallback((k) => t(k, lang), [lang]);

  const inputStyle = {
    background: 'var(--bg)', border: '1px solid var(--line)',
    color: 'var(--ink)', padding: '8px 12px', fontSize: 13,
    fontFamily: 'var(--font-mono)', width: '100%', boxSizing: 'border-box',
  };

  const [subPage, setSubPage] = React.useState('lobby');
  const [gameId, setGameId] = React.useState(null);
  const [token, setToken] = React.useState('');
  const [faction, setFaction] = React.useState('');
  const [error, setError] = React.useState('');
  const [loading, setLoading] = React.useState(false);

  // localStorage helpers
  const getPid = () => typeof localStorage !== 'undefined' ? localStorage.getItem('tka_player_id') || '' : '';
  const setPid = (v) => { try { if (typeof localStorage !== 'undefined') localStorage.setItem('tka_player_id', v); } catch(e) {} };
  const parseStoredTokens = () => {
    try { return JSON.parse((typeof localStorage !== 'undefined' ? localStorage.getItem('tka_game_tokens') : null) || '{}'); } catch(e) { return {}; }
  };
  const saveToken = (gid, tok, fac) => {
    if (typeof localStorage === 'undefined') return;
    try {
      const data = parseStoredTokens();
      data[gid] = { token: tok, faction: fac };
      localStorage.setItem('tka_game_tokens', JSON.stringify(data));
    } catch(e) {}
  };

  // ── Lobby ─────────────────────────────────────────────
  const [lobbyGames, setLobbyGames] = React.useState([]);
  const [lobbyLoading, setLobbyLoading] = React.useState(true);

  const loadLobby = () => {
    setLobbyLoading(true);
    fetchLobby().then(games => {
      setLobbyGames(games || []);
      setLobbyLoading(false);
    }).catch(err => {
      setLobbyGames([]);
      setLobbyLoading(false);
      setError(lang === '中' ? '加载大厅失败: ' + (err?.message || err) : 'Failed to load lobby: ' + (err?.message || err));
    });
  };

  React.useEffect(() => {
    if (subPage === 'lobby') loadLobby();
  }, [subPage]);

  // ── Create form ──────────────────────────────────────
  const [cfTitle, setCfTitle] = React.useState('');
  const [cfMode, setCfMode] = React.useState('managed');
  const [cfAgentName, setCfAgentName] = React.useState('');
  const [cfFaction, setCfFaction] = React.useState('');
  const [cfPersona, setCfPersona] = React.useState('');
  const [cfProvider, setCfProvider] = React.useState('deepseek');
  const [cfModel, setCfModel] = React.useState('deepseek-chat');
  const [cfApiKey, setCfApiKey] = React.useState('');

  const doCreate = async () => {
    if (!cfTitle.trim()) { setError(lang === '中' ? '请输入房间标题' : 'Please enter a title'); return; }
    if (!cfAgentName.trim()) { setError(lang === '中' ? '请输入 Agent 名称' : 'Please enter agent name'); return; }
    if (!cfFaction) { setError(lang === '中' ? '请选择势力' : 'Please select a faction'); return; }
    setLoading(true); setError('');
    try {
      const pid = getPid();
      const result = await createPvpGame(cfTitle.trim(), pid || undefined, 35);
      setLoading(false);
      if (result && result.game_id) {
        if (result.player_id) setPid(result.player_id);
        setGameId(result.game_id);
        setToken(result.token);
        setFaction(cfFaction);
        saveToken(result.game_id, result.token, cfFaction);
        setSubPage('room');
      } else {
        setError(result?.error || 'Create failed');
      }
    } catch(err) {
      setLoading(false);
      setError(lang === '中' ? '创建失败: ' + (err?.message || err) : 'Create failed: ' + (err?.message || err));
    }
  };

  // ── Join form ────────────────────────────────────────
  const [joinGid, setJoinGid] = React.useState(null);
  const [joinMode, setJoinMode] = React.useState('managed');
  const [jfAgentName, setJfAgentName] = React.useState('');
  const [jfFaction, setJfFaction] = React.useState('');
  const [jfPersona, setJfPersona] = React.useState('');
  const [jfProvider, setJfProvider] = React.useState('deepseek');
  const [jfModel, setJfModel] = React.useState('deepseek-chat');
  const [jfApiKey, setJfApiKey] = React.useState('');
  const [jfAgentId, setJfAgentId] = React.useState('');
  const [jfSecret, setJfSecret] = React.useState('');
  const [joinResult, setJoinResult] = React.useState(null);

  const openJoin = (gid) => {
    setJoinGid(gid);
    setJoinMode('managed');
    setJfAgentName(''); setJfFaction(''); setJfPersona(''); setJfProvider('deepseek');
    setJfModel('deepseek-chat'); setJfApiKey(''); setJfAgentId(''); setJfSecret('');
    setJoinResult(null); setError('');
  };

  const doJoin = async () => {
    if (!jfFaction) { setError(lang === '中' ? '请选择势力' : 'Please select a faction'); return; }
    setLoading(true); setError(''); setJoinResult(null);
    try {
      const pid = getPid();

      if (joinMode === 'managed') {
        if (!jfAgentName.trim()) { setError(lang === '中' ? '请输入 Agent 名称' : 'Please enter agent name'); setLoading(false); return; }
        let llmConfig = null;
        if (jfProvider !== 'mock') {
          llmConfig = { provider: jfProvider, model: jfModel };
          if (jfApiKey) llmConfig.api_key = jfApiKey;
        } else {
          llmConfig = { provider: 'mock' };
        }
        const result = await joinManaged(joinGid, pid || undefined, jfAgentName.trim(), jfFaction, llmConfig, jfPersona || undefined);
        setLoading(false);
        if (result && result.token) {
          setGameId(result.game_id);
          setToken(result.token);
          setFaction(result.faction);
          saveToken(result.game_id, result.token, result.faction);
          setJoinGid(null);
          setSubPage('room');
        } else {
          setError(result?.error || 'Join failed');
        }
      } else {
        if (!jfAgentId.trim() || !jfSecret.trim()) {
          setError(lang === '中' ? '请输入 agent_id 和 secret' : 'Please enter agent_id and secret');
          setLoading(false); return;
        }
        const result = await joinSelfHosted(joinGid, jfAgentId.trim(), jfSecret.trim(), jfFaction);
        setLoading(false);
        if (result && result.token) {
          setJoinResult(result);
          setToken(result.token);
          saveToken(joinGid, result.token, jfFaction);
        } else {
          setError(result?.error || 'Join failed');
        }
      }
    } catch(err) {
      setLoading(false);
      setError(lang === '中' ? '加入失败: ' + (err?.message || err) : 'Join failed: ' + (err?.message || err));
    }
  };

  // ── My Games ──────────────────────────────────────────
  const [myGames, setMyGames] = React.useState([]);
  const [myGamesLoading, setMyGamesLoading] = React.useState(true);

  const loadMyGames = () => {
    setMyGamesLoading(true);
    const pid = getPid();
    if (pid) {
      fetchMyGames(pid).then(games => {
        setMyGames(games || []);
        setMyGamesLoading(false);
      }).catch(err => {
        setMyGames([]);
        setMyGamesLoading(false);
        setError(lang === '中' ? '加载我的对局失败' : 'Failed to load my games');
      });
    } else {
      setMyGames([]);
      setMyGamesLoading(false);
    }
  };

  React.useEffect(() => {
    if (subPage === 'my-games') loadMyGames();
  }, [subPage]);

  const openMyGame = (gid) => {
    const data = parseStoredTokens();
    const entry = data[gid];
    setGameId(gid);
    setToken(entry?.token || '');
    setFaction(entry?.faction || '');
    setSubPage('room');
  };

  // ── Room ──────────────────────────────────────────────
  const [liveState, setLiveState] = React.useState(null);

  React.useEffect(() => {
    if (subPage !== 'room' || !gameId) return;
    const poll = () => {
      fetchLiveGame(gameId).then(data => {
        if (data) setLiveState(data);
      }).catch(() => {});
    };
    poll();
    const iv = setInterval(poll, 2000);
    return () => clearInterval(iv);
  }, [subPage, gameId]);

  const doStartGame = async () => {
    if (!token) return;
    setLoading(true); setError('');
    try {
      const result = await startGame(gameId, token);
      setLoading(false);
      if (result && result.error) setError(result.error);
    } catch(err) {
      setLoading(false);
      setError(lang === '中' ? '开始对局失败' : 'Failed to start game');
    }
  };

  const doSurrender = async () => {
    if (!token) return;
    setLoading(true);
    try {
      const result = await surrenderGame(gameId, token);
      setLoading(false);
      if (result && result.error) setError(result.error);
    } catch(err) {
      setLoading(false);
      setError(lang === '中' ? '投降失败' : 'Failed to surrender');
    }
  };

  // ── LLM Provider options ──────────────────────────────
  const providers = [
    { id: 'deepseek', name: 'DeepSeek', defaultModel: 'deepseek-chat' },
    { id: 'openai', name: 'OpenAI', defaultModel: 'gpt-4o' },
    { id: 'mock', name: lang === '中' ? '模拟' : 'Mock', defaultModel: 'mock' },
  ];

  // ── Render ────────────────────────────────────────────

  // ── Join dialog ───────────────────────────────────────
  if (joinGid) {
    return React.createElement('section', { className: 'arena' },
      React.createElement('div', { className: 'docs-head' },
        React.createElement('h1', { className: 'docs-h1' }, lang === '中' ? '加入对局 #' + joinGid : 'Join Game #' + joinGid),
        React.createElement('p', { className: 'docs-sub' }, lang === '中' ? '选择你的势力并配置 Agent' : 'Choose your faction and configure your agent')
      ),
      error && React.createElement('div', {
        style: { color: 'var(--accent)', padding: '10px 16px', background: 'rgba(179,66,55,0.1)', border: '1px solid var(--accent)', marginBottom: 16, fontSize: 13 }
      }, error),

      React.createElement('div', { style: { display: 'flex', gap: 8, marginBottom: 16 } },
        React.createElement('button', {
          className: 'btn-ghost btn-sm', style: joinMode === 'managed' ? { background: 'var(--gold-dim)', color: 'var(--ink)' } : {},
          onClick: () => setJoinMode('managed')
        }, lang === '中' ? '托管模式' : 'Managed'),
        React.createElement('button', {
          className: 'btn-ghost btn-sm', style: joinMode === 'self_hosted' ? { background: 'var(--gold-dim)', color: 'var(--ink)' } : {},
          onClick: () => setJoinMode('self_hosted')
        }, lang === '中' ? '自主模式' : 'Self-hosted'),
      ),

      React.createElement('div', { style: { marginBottom: 16 } },
        React.createElement('label', { style: { display: 'block', color: 'var(--ink-mute)', fontSize: 12, marginBottom: 4 } }, lang === '中' ? '势力' : 'Faction'),
        React.createElement('div', { style: { display: 'flex', gap: 8 } },
          Object.entries(FACTIONS).map(([k, f]) =>
            React.createElement('button', {
              key: k,
              className: 'btn-ghost', style: { borderColor: f.color, color: f.color, background: jfFaction === k ? f.color + '22' : 'transparent' },
              onClick: () => setJfFaction(k)
            }, (lang === '中' ? k + ' ' + f.leader : k + ' · ' + f.leaderEn))
          )
        )
      ),

      joinMode === 'managed' && React.createElement('div', null,
        React.createElement('label', { style: { display: 'block', color: 'var(--ink-mute)', fontSize: 12, marginBottom: 4 } },
          lang === '中' ? 'Agent 名称' : 'Agent name'),
        React.createElement('input', {
          value: jfAgentName, onChange: (e) => setJfAgentName(e.target.value),
          style: inputStyle, placeholder: lang === '中' ? '如: 关羽' : 'e.g. Guan Yu'
        }),
        React.createElement('label', { style: { display: 'block', color: 'var(--ink-mute)', fontSize: 12, marginBottom: 4, marginTop: 12 } },
          lang === '中' ? '性格描述 (persona)' : 'Persona'),
        React.createElement('textarea', {
          value: jfPersona, onChange: (e) => setJfPersona(e.target.value),
          style: { ...inputStyle, minHeight: 60, resize: 'vertical' },
          placeholder: lang === '中' ? '如: 关羽性格，忠义勇猛...' : 'e.g. Loyal and brave...'
        }),
        React.createElement('label', { style: { display: 'block', color: 'var(--ink-mute)', fontSize: 12, marginBottom: 4, marginTop: 12 } },
          'LLM Provider'),
        React.createElement('div', { style: { display: 'flex', gap: 8, marginBottom: 8 } },
          providers.map((p) =>
            React.createElement('button', {
              key: p.id,
              className: 'btn-ghost btn-sm', style: jfProvider === p.id ? { background: 'var(--gold-dim)', color: 'var(--ink)' } : {},
              onClick: () => { setJfProvider(p.id); setJfModel(p.defaultModel); }
            }, p.name)
          )
        ),
        jfProvider !== 'mock' && React.createElement('div', null,
          React.createElement('input', {
            value: jfModel, onChange: (e) => setJfModel(e.target.value),
            style: inputStyle, placeholder: 'Model name (uses server env key)'
          }),
        ),
      ),

      joinMode === 'self_hosted' && React.createElement('div', null,
        React.createElement('label', { style: { display: 'block', color: 'var(--ink-mute)', fontSize: 12, marginBottom: 4 } },
          'Agent ID'),
        React.createElement('input', {
          value: jfAgentId, onChange: (e) => setJfAgentId(e.target.value),
          style: inputStyle, placeholder: '从 /agents/register 获得'
        }),
        React.createElement('label', { style: { display: 'block', color: 'var(--ink-mute)', fontSize: 12, marginBottom: 4, marginTop: 12 } },
          'Secret'),
        React.createElement('input', {
          value: jfSecret, onChange: (e) => setJfSecret(e.target.value),
          style: inputStyle, placeholder: 'secret'
        }),
      ),

      joinResult && React.createElement('div', {
        style: { background: 'var(--panel)', border: '1px solid var(--line)', padding: 16, marginTop: 12 }
      },
        React.createElement('p', { style: { color: 'var(--gold)', fontSize: 13, marginBottom: 8 } },
          lang === '中' ? '已加入对局！你的 token:' : 'Joined! Your token:'),
        React.createElement('code', { style: { fontSize: 12, wordBreak: 'break-all', color: 'var(--gold-dim)' } }, token),
        React.createElement('p', { style: { color: 'var(--ink-mute)', fontSize: 11, marginTop: 8 } },
          lang === '中' ? '现在用你的 agent 程序通过 API 提交动作。进入房间页可观战。' : 'Now use your agent process to submit actions via API. Go to the room to spectate.')
      ),

      React.createElement('div', { style: { marginTop: 16, display: 'flex', gap: 8 } },
        React.createElement('button', { className: 'btn-ghost', onClick: () => setJoinGid(null) },
          '← ' + (lang === '中' ? '返回大厅' : 'Back to lobby')),
        !joinResult && React.createElement('button', { className: 'btn-primary', onClick: doJoin, disabled: loading },
          loading ? '…' : (lang === '中' ? '加入对局' : 'Join game') + ' →'),
        joinResult && React.createElement('button', { className: 'btn-primary', onClick: () => { setJoinGid(null); setSubPage('room'); } },
          (lang === '中' ? '进入房间' : 'Go to room') + ' →'),
      )
    );
  }

  // ── My Games page ─────────────────────────────────────
  if (subPage === 'my-games') {
    return React.createElement('section', { className: 'arena' },
      React.createElement('div', { className: 'docs-head' },
        React.createElement('h1', { className: 'docs-h1' }, lang === '中' ? '我的对局' : 'My Games'),
        React.createElement('p', { className: 'docs-sub' }, lang === '中' ? '你参与的所有 PvP 对局' : 'All PvP games you participate in')
      ),
      React.createElement('button', { className: 'btn-ghost btn-sm', onClick: () => setSubPage('lobby'), style: { marginBottom: 16 } },
        '← ' + (lang === '中' ? '返回大厅' : 'Back to lobby')),
      myGamesLoading ? React.createElement('div', { style: { padding: 20, textAlign: 'center', color: 'var(--ink-mute)' } }, '...')
      : myGames.length === 0 ? React.createElement('div', { style: { padding: 20, textAlign: 'center', color: 'var(--ink-mute)' } },
        lang === '中' ? '还没有对局。创建或加入一局吧！' : 'No games yet. Create or join one!')
      : React.createElement('div', { className: 'battle-list' },
        myGames.map((g) => {
          const statusLabel = { waiting: lang === '中' ? '等待中' : 'Waiting', active: lang === '中' ? '进行中' : 'Active', finished: lang === '中' ? '已结束' : 'Finished' }[g.status] || g.status;
          return React.createElement('div', { key: g.game_id, className: 'battle-row' },
            React.createElement('div', { className: 'b-id' }, '#' + g.game_id),
            React.createElement('div', { className: 'b-mid' },
              React.createElement('div', { className: 'b-line1' },
                React.createElement('span', { className: 'b-model' }, g.title || ('Game #' + g.game_id)),
                React.createElement('span', { className: 'b-pip', style: { color: g.status === 'active' ? '#e0a040' : g.status === 'finished' ? '#60a060' : 'var(--ink-mute)' } }, statusLabel),
              ),
              React.createElement('div', { className: 'b-line2' },
                React.createElement('span', null, 'Tick: ' + g.tick),
                g.winner && React.createElement('span', null,
                  lang === '中' ? '胜者: ' : 'Winner: ',
                  React.createElement('b', { style: { color: (FACTIONS[g.winner] || {}).color || 'var(--ink)' } }, g.winner)),
                React.createElement('span', null, (g.agents || []).map((a) => a.faction).join(', ')),
              ),
            ),
            React.createElement('div', { className: 'b-actions' },
              g.status !== 'finished' && React.createElement('button', {
                className: 'btn-ghost btn-sm', onClick: () => openMyGame(g.game_id)
              }, (lang === '中' ? '进入观战' : 'Spectate') + ' →'),
            ),
          );
        })
      )
    );
  }

  // ── Room page ──────────────────────────────────────────
  if (subPage === 'room' && gameId) {
    const ls = liveState;
    const status = ls?.status || 'waiting';
    const statusLabel = { waiting: lang === '中' ? '等待中' : 'Waiting', active: lang === '中' ? '进行中' : 'Active', finished: lang === '中' ? '已结束' : 'Finished' }[status] || status;
    const storedTokens = parseStoredTokens();
    const isHost = ls?.agents && token && ls.agents.some(a => a.faction === (storedTokens[gameId]?.faction || ''));

    return React.createElement('section', { className: 'arena' },
      React.createElement('div', { className: 'docs-head' },
        React.createElement('h1', { className: 'docs-h1' },
          lang === '中' ? '对战房间 #' + gameId : 'Game Room #' + gameId),
        React.createElement('p', { className: 'docs-sub' },
          React.createElement('span', { style: { color: status === 'active' ? '#e0a040' : status === 'finished' ? '#60a060' : 'var(--ink-mute)' } }, statusLabel),
          ' · Tick ' + (ls?.tick || 0),
          ls?.winner && React.createElement('span', { style: { marginLeft: 8, color: (FACTIONS[ls.winner] || {}).color || 'var(--gold)' } },
            lang === '中' ? '胜者: ' + ls.winner : 'Winner: ' + ls.winner)
        )
      ),
      React.createElement('button', { className: 'btn-ghost btn-sm', onClick: () => { setSubPage('lobby'); setGameId(null); setLiveState(null); }, style: { marginBottom: 16 } },
        '← ' + (lang === '中' ? '返回大厅' : 'Back to lobby')),

      // Agent slots
      React.createElement('div', { style: { display: 'flex', gap: 12, marginBottom: 16, flexWrap: 'wrap' } },
        (ls?.agents || []).map((a) => {
          const f = FACTIONS[a.faction] || {};
          return React.createElement('div', { key: a.id || a.faction, style: {
            flex: 1, minWidth: 160, background: 'var(--panel)', border: '1px solid ' + f.color, padding: 12,
            opacity: a.submitted ? 1 : 0.7,
          }},
            React.createElement('div', { style: { color: f.color, fontWeight: 600, fontSize: 14 } },
              (lang === '中' ? a.faction : (FACTIONS[a.faction]||{}).en || a.faction) + ' · ' + a.name),
            React.createElement('div', { style: { color: 'var(--ink-mute)', fontSize: 11, marginTop: 4 } },
              (a.mode === 'managed' ? (lang === '中' ? '托管' : 'Managed') : (lang === '中' ? '自主' : 'Self-hosted')) +
              ' · ' + (a.submitted ? (lang === '中' ? '已提交' : 'Submitted') : (lang === '中' ? '等待中' : 'Waiting'))),
          );
        })
      ),

      error && React.createElement('div', {
        style: { color: 'var(--accent)', padding: '10px 16px', background: 'rgba(179,66,55,0.1)', border: '1px solid var(--accent)', marginBottom: 16, fontSize: 13 }
      }, error),

      // ── Invite friends section (shown while waiting) ──
      status === 'waiting' && React.createElement('div', { style: {
        background: 'var(--panel)', border: '1px solid var(--gold-dim)', padding: 16,
        marginBottom: 8, marginTop: 16,
      }},
        React.createElement('div', { style: { color: 'var(--gold)', fontWeight: 600, fontSize: 14, marginBottom: 12 } },
          lang === '中' ? '邀请朋友' : 'Invite Friends'),
        React.createElement('p', { style: { color: 'var(--ink-mute)', fontSize: 11, marginBottom: 8 } },
          lang === '中' ? '朋友可以用任意名称和未占用的势力一键加入' : 'Friends can join with any name and available faction'),
        // Quick-join URL
        React.createElement('div', { style: { marginBottom: 8 } },
          React.createElement('div', { style: { color: 'var(--ink-mute)', fontSize: 10, marginBottom: 2 } },
            lang === '中' ? '快速加入链接:' : 'Quick-join URL:'),
          React.createElement('div', { style: { display: 'flex', gap: 6 } },
            React.createElement('code', { style: {
              flex: 1, background: 'var(--bg)', padding: '6px 10px', fontSize: 11,
              color: 'var(--gold-dim)', overflow: 'auto', whiteSpace: 'nowrap',
              border: '1px solid var(--line)', fontFamily: 'var(--font-mono)',
            } }, (window.location.origin || '') + '/join/' + gameId),
            React.createElement('button', {
              className: 'btn-ghost btn-sm',
              onClick: () => { try { navigator.clipboard.writeText((window.location.origin || '') + '/join/' + gameId); } catch(e) {} },
            }, lang === '中' ? '复制' : 'Copy'),
          )
        ),
        // Curl example
        React.createElement('div', null,
          React.createElement('div', { style: { color: 'var(--ink-mute)', fontSize: 10, marginBottom: 2 } },
            lang === '中' ? '或通过 curl 加入:' : 'Or join via curl:'),
          React.createElement('div', { style: { display: 'flex', gap: 6 } },
            React.createElement('code', { style: {
              flex: 1, background: 'var(--bg)', padding: '6px 10px', fontSize: 11,
              color: 'var(--gold-dim)', overflow: 'auto', whiteSpace: 'nowrap',
              border: '1px solid var(--line)', fontFamily: 'var(--font-mono)',
            } }, "curl -s -X POST \"" + (window.location.origin || 'http://localhost:8000') + '/join/' + gameId + "\" -H \"Content-Type: application/json\" -d '{\"name\":\"关羽\",\"faction\":\"蜀\"}'"),
            React.createElement('button', {
              className: 'btn-ghost btn-sm',
              onClick: () => { try { navigator.clipboard.writeText("curl -s -X POST \"" + (window.location.origin || 'http://localhost:8000') + '/join/' + gameId + "\" -H \"Content-Type: application/json\" -d '{\"name\":\"关羽\",\"faction\":\"蜀\"}'"); } catch(e) {} },
            }, lang === '中' ? '复制' : 'Copy'),
          )
        ),
      ),

      // Waiting — start button for host
      status === 'waiting' && React.createElement('div', { style: { textAlign: 'center', padding: 20 } },
        React.createElement('p', { style: { color: 'var(--ink-mute)', fontSize: 13, marginBottom: 12 } },
          lang === '中' ? '等待玩家加入... (需全部三个势力都有人)' : 'Waiting for players... (all 3 factions needed)'),
        React.createElement('button', { className: 'btn-primary', onClick: doStartGame, disabled: loading },
          loading ? '…' : (lang === '中' ? '开始对局' : 'Start Game') + ' ▶'),
      ),

      // Active — live map + events
      status === 'active' && ls && React.createElement('div', null,
        // Mini map
        React.createElement('div', { style: { marginBottom: 16 } },
          React.createElement('div', { className: 'code-cap' }, lang === '中' ? '城池态势' : 'City status'),
          React.createElement('div', { style: { display: 'flex', gap: 8, flexWrap: 'wrap' } },
            (ls.cities || []).map((c) => {
              const fc = c.owner ? ((FACTIONS[c.owner] || {}).color || '#998') : '#998';
              return React.createElement('div', { key: c.name, style: {
                background: 'var(--panel)', border: '1px solid ' + fc, padding: '8px 12px', minWidth: 100
              }},
                React.createElement('div', { style: { color: fc, fontWeight: 600, fontSize: 13 } }, c.name),
                React.createElement('div', { style: { color: 'var(--ink-mute)', fontSize: 11, marginTop: 2 } },
                  (c.owner || (lang === '中' ? '中立' : 'Neutral')) + ' · ' + (c.troops || 0) + ' ' + (lang === '中' ? '兵' : 'troops')),
              );
            })
          ),
        ),

        // Events
        React.createElement('div', { style: { marginBottom: 16 } },
          React.createElement('div', { className: 'code-cap' }, lang === '中' ? '最近事件' : 'Recent events'),
          React.createElement('div', { style: { background: 'var(--panel)', border: '1px solid var(--line)', padding: 10, maxHeight: 160, overflowY: 'auto' } },
            (ls.events || []).length === 0 && !(ls.diplomacy || []).length
              ? React.createElement('div', { style: { color: 'var(--ink-mute)', fontSize: 12 } }, '—')
              : [
                ...(ls.events || []).map((e, i) => {
                  const ec = (FACTIONS[e.captured_by || e.defended_by] || {}).color || 'var(--gold)';
                  return React.createElement('div', { key: 'e' + i, style: { color: ec, fontSize: 12, padding: '2px 0' } },
                    '⚔ ' + (e.city || '?') + ': ' + (e.result === 'captured' ? (e.captured_by + ' ' + (lang === '中' ? '攻占' : 'captured') + ' ← ' + (e.from || '?')) : ((e.defended_by || '?') + ' ' + (lang === '中' ? '守住' : 'defended'))));
                }),
                ...(ls.diplomacy || []).map((d, i) =>
                  React.createElement('div', { key: 'd' + i, style: { color: 'var(--gold-dim)', fontSize: 12, padding: '2px 0' } },
                    '✉ ' + d.from_faction + ': ' + d.message)
                ),
              ]
          )
        ),

        // Surrender button
        isHost && React.createElement('div', { style: { textAlign: 'center', marginTop: 12 } },
          React.createElement('button', { className: 'btn-ghost btn-sm', onClick: doSurrender, disabled: loading,
            style: { color: 'var(--accent)', borderColor: 'var(--accent)' } },
            loading ? '…' : (lang === '中' ? '投降' : 'Surrender')),
        ),
      ),

      // Finished
      status === 'finished' && React.createElement('div', { style: { textAlign: 'center', padding: 30 } },
        React.createElement('div', { style: { fontSize: 24, color: (FACTIONS[ls?.winner] || {}).color || 'var(--gold)', fontWeight: 700, marginBottom: 8 } },
          (ls?.winner || '?') + ' ' + (lang === '中' ? '一统天下！' : 'unifies the realm!')),
        React.createElement('p', { style: { color: 'var(--ink-mute)', fontSize: 13 } },
          lang === '中' ? '对局已结束' : 'Game over'),
      ),
    );
  }

  // ── Create page ────────────────────────────────────────
  if (subPage === 'create') {
    return React.createElement('section', { className: 'arena' },
      React.createElement('div', { className: 'docs-head' },
        React.createElement('h1', { className: 'docs-h1' }, lang === '中' ? '创建对战' : 'Create Game'),
        React.createElement('p', { className: 'docs-sub' }, lang === '中' ? '创建一个新的 PvP 对局房间' : 'Create a new PvP game room')
      ),
      React.createElement('button', { className: 'btn-ghost btn-sm', onClick: () => setSubPage('lobby'), style: { marginBottom: 16 } },
        '← ' + (lang === '中' ? '返回大厅' : 'Back to lobby')),
      error && React.createElement('div', {
        style: { color: 'var(--accent)', padding: '10px 16px', background: 'rgba(179,66,55,0.1)', border: '1px solid var(--accent)', marginBottom: 16, fontSize: 13 }
      }, error),

      React.createElement('div', { style: { maxWidth: 500 } },
        React.createElement('label', { style: { display: 'block', color: 'var(--ink-mute)', fontSize: 12, marginBottom: 4 } },
          lang === '中' ? '房间标题' : 'Room title'),
        React.createElement('input', { value: cfTitle, onChange: (e) => setCfTitle(e.target.value),
          style: inputStyle, placeholder: lang === '中' ? '给房间起个名字' : 'Name your room' }),

        React.createElement('label', { style: { display: 'block', color: 'var(--ink-mute)', fontSize: 12, marginBottom: 4, marginTop: 16 } },
          lang === '中' ? 'Agent 名称' : 'Agent name'),
        React.createElement('input', { value: cfAgentName, onChange: (e) => setCfAgentName(e.target.value),
          style: inputStyle, placeholder: lang === '中' ? '如: 诸葛亮' : 'e.g. Zhuge Liang' }),

        React.createElement('label', { style: { display: 'block', color: 'var(--ink-mute)', fontSize: 12, marginBottom: 4, marginTop: 16 } },
          lang === '中' ? '选择势力' : 'Choose faction'),
        React.createElement('div', { style: { display: 'flex', gap: 8 } },
          Object.entries(FACTIONS).map(([k, f]) =>
            React.createElement('button', {
              key: k,
              className: 'btn-ghost', style: { borderColor: f.color, color: f.color, background: cfFaction === k ? f.color + '22' : 'transparent' },
              onClick: () => setCfFaction(k)
            }, (lang === '中' ? k + ' ' + f.leader : k + ' · ' + f.leaderEn))
          )
        ),

        React.createElement('label', { style: { display: 'block', color: 'var(--ink-mute)', fontSize: 12, marginBottom: 4, marginTop: 16 } },
          lang === '中' ? '性格描述 (persona) - 可选' : 'Persona (optional)'),
        React.createElement('textarea', { value: cfPersona, onChange: (e) => setCfPersona(e.target.value),
          style: { ...inputStyle, minHeight: 60, resize: 'vertical' },
          placeholder: lang === '中' ? '如: 关羽性格，忠义勇猛...' : 'e.g. Loyal and brave...' }),

        React.createElement('label', { style: { display: 'block', color: 'var(--ink-mute)', fontSize: 12, marginBottom: 4, marginTop: 16 } },
          'LLM Provider'),
        React.createElement('div', { style: { display: 'flex', gap: 8, marginBottom: 8 } },
          providers.map((p) =>
            React.createElement('button', {
              key: p.id,
              className: 'btn-ghost btn-sm', style: cfProvider === p.id ? { background: 'var(--gold-dim)', color: 'var(--ink)' } : {},
              onClick: () => { setCfProvider(p.id); setCfModel(p.defaultModel); }
            }, p.name)
          )
        ),
        cfProvider !== 'mock' && React.createElement('div', null,
          React.createElement('input', { value: cfModel, onChange: (e) => setCfModel(e.target.value),
            style: inputStyle, placeholder: 'Model name (uses server env key)' }),
        ),

        React.createElement('div', { style: { marginTop: 24 } },
          React.createElement('button', { className: 'btn-primary', onClick: doCreate, disabled: loading },
            loading ? '…' : (lang === '中' ? '创建对局' : 'Create game') + ' ▶'),
        ),
      )
    );
  }

  // ── Lobby main page ────────────────────────────────────
  return React.createElement('section', { className: 'arena' },
    React.createElement('div', { className: 'docs-head' },
      React.createElement('h1', { className: 'docs-h1' }, lang === '中' ? '对战大厅' : 'Arena Lobby'),
      React.createElement('p', { className: 'docs-sub' }, lang === '中' ? '创建或加入 PvP 对局，与真人玩家对战' : 'Create or join PvP games against human players')
    ),
    React.createElement('div', { style: { display: 'flex', gap: 8, marginBottom: 24 } },
      React.createElement('button', { className: 'btn-primary', onClick: () => setSubPage('create') },
        lang === '中' ? '创建对局' : 'Create game' + ' +'),
      React.createElement('button', { className: 'btn-ghost', onClick: () => setSubPage('my-games') },
        lang === '中' ? '我的对局' : 'My games'),
      React.createElement('button', { className: 'btn-ghost', onClick: loadLobby },
        lang === '中' ? '刷新' : 'Refresh' + ' ↻'),
    ),

    error && React.createElement('div', {
      style: { color: 'var(--accent)', padding: '10px 16px', background: 'rgba(179,66,55,0.1)', border: '1px solid var(--accent)', marginBottom: 16, fontSize: 13 }
    }, error),

    lobbyLoading ? React.createElement('div', { style: { padding: 20, textAlign: 'center', color: 'var(--ink-mute)' } }, '...')
    : lobbyGames.length === 0 ? React.createElement('div', { style: { padding: 40, textAlign: 'center', color: 'var(--ink-mute)' } },
      lang === '中' ? '暂无开放对局。创建一局吧！' : 'No open games. Create one!')
    : React.createElement('div', { className: 'battle-list' },
      lobbyGames.map((g) => {
        const filledSlots = Object.values(g.slots || {}).filter(Boolean).length;
        return React.createElement('div', { key: g.game_id, className: 'battle-row' },
          React.createElement('div', { className: 'b-id' }, '#' + g.game_id),
          React.createElement('div', { className: 'b-mid' },
            React.createElement('div', { className: 'b-line1' },
              React.createElement('span', { className: 'b-model' }, g.title || ('Game #' + g.game_id)),
              g.host_name && React.createElement('span', { style: { color: 'var(--gold-dim)', fontSize: 11, marginLeft: 8 } },
                (lang === '中' ? '房主: ' : 'Host: ') + g.host_name),
            ),
            React.createElement('div', { className: 'b-line2' },
              React.createElement('span', null, filledSlots + '/3 ' + (lang === '中' ? '已加入' : 'joined')),
              Object.entries(g.slots || {}).map(([f, name]) =>
                React.createElement('span', { key: f, style: { color: name ? (FACTIONS[f] || {}).color || 'var(--ink)' : 'var(--ink-mute)' } },
                  f + ': ' + (name || '—'))
              ),
            ),
          ),
          React.createElement('div', { className: 'b-actions' },
            filledSlots < 3 && React.createElement('button', {
              className: 'btn-ghost btn-sm', onClick: () => openJoin(g.game_id)
            }, (lang === '中' ? '加入' : 'Join') + ' →'),
          ),
        );
      })
    )
  );
}

window.ArenaSection = ArenaSection;


