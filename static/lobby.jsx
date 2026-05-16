// ═══════════════════════════════════════════════════════════════
// lobby.jsx — 对局大厅 · BYOA 一键接入
// ═══════════════════════════════════════════════════════════════

// ── API helpers ─────────────────────────────────────────────────
async function fetchLobbyStatus() {
  try {
    const resp = await fetch(apiUrl('/v1/lobby/status'));
    if (!resp.ok) throw new Error('API error');
    return await resp.json();
  } catch (e) { return null; }
}

async function joinLobby(faction) {
  try {
    const resp = await fetch(apiUrl('/v1/lobby/join'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ faction }),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      return { error: err.detail || resp.statusText, status: resp.status };
    }
    return await resp.json();
  } catch (e) { return { error: 'Network error' }; }
}

async function fetchInstruction(token) {
  try {
    const resp = await fetch(apiUrl('/v1/lobby/instruction?token=' + encodeURIComponent(token)));
    if (!resp.ok) throw new Error('API error');
    return await resp.text();
  } catch (e) { return null; }
}

// ── Slot card — 5 visual states ──────────────────────────────────
function SlotCard({ faction, slot, lang, gameStatus, countdownDeadline }) {
  const f = FACTIONS[faction];
  const status = slot.status;
  const isOpen = status === 'open';
  const isOccupied = status === 'occupied';
  const isDisconnected = status === 'disconnected';
  const isReady = slot.ready === true;
  const isCountdown = gameStatus === 'countdown';

  let statusText, statusIcon, statusClass, readyBadge = null;

  if (isOpen) {
    statusText = lang === '中' ? '空缺 · 等待接入' : 'Open · Waiting';
    statusIcon = '◎';
    statusClass = 'slot-open';
  } else if (isOccupied) {
    if (isReady) {
      statusText = lang === '中' ? '已就绪 · 等待开战' : 'Ready · Awaiting start';
      statusIcon = '◆';
      statusClass = 'slot-ready';
      if (isCountdown) {
        statusClass = 'slot-countdown';
      }
    } else {
      const online = slot.online_sec != null ? `${slot.online_sec}s` : '';
      statusText = (lang === '中' ? '已接入 · 等待就绪' : 'Joined · Awaiting ready') + (online ? ` · ${online}` : '');
      statusIcon = '◇';
      statusClass = 'slot-occupied';
      readyBadge = (
        <span className="ready-badge not-ready">
          {lang === '中' ? '未就绪' : 'Not Ready'}
        </span>
      );
    }
  } else if (isDisconnected) {
    const sec = slot.disconnected_sec || 0;
    const remain = slot.reconnect_remaining_sec || 0;
    const min = Math.floor(remain / 60);
    const s = remain % 60;
    statusText = (lang === '中' ? '⏸ 掉线' : '⏸ DC') + ` · ${sec}s · ${min}m${s}s ${lang === '中' ? '后释放' : 'left'}`;
    statusIcon = '⏸';
    statusClass = 'slot-disconnected';
  }

  return (
    <div className={'slot-card ' + statusClass} style={{ '--fc': f.color }}>
      <div className="slot-faction">
        <span className="slot-glyph">{f.glyph}</span>
        <span className="slot-name">{lang === '中' ? faction : f.en}</span>
        <span className="slot-leader">{f.leader}</span>
        {slot.agent_display_name && (
          <span className="slot-agent-name" title={slot.agent_display_name}>
            {slot.agent_display_name}
          </span>
        )}
      </div>
      <div className="slot-status">
        <span className="slot-icon">{statusIcon}</span>
        <span className="slot-text">{statusText}</span>
      </div>
      {readyBadge}
      {!isOpen && slot.ip && (
        <div className="slot-ip" title={slot.ip}>{slot.ip}</div>
      )}
    </div>
  );
}

// ── Lobby status bar component ──────────────────────────────────
function LobbyStatusBar({ g, tick, maxTicks, lang }) {
  const [now, setNow] = React.useState(Date.now());

  React.useEffect(() => {
    const iv = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(iv);
  }, []);

  const status = g ? g.status : 'lobby';
  let statusText, statusColor, statusDot;

  if (status === 'finished') {
    statusText = lang === '中' ? '已结束' : 'Finished';
    statusColor = 'var(--accent)';
    statusDot = '●';
  } else if (status === 'active') {
    statusText = lang === '中' ? '进行中' : 'LIVE';
    statusColor = 'var(--gold)';
    statusDot = '●';
  } else if (status === 'paused') {
    statusText = lang === '中' ? '已暂停' : 'Paused';
    statusColor = 'var(--accent)';
    statusDot = '⏸';
  } else if (status === 'countdown') {
    statusText = lang === '中' ? '倒计时' : 'Countdown';
    statusColor = 'var(--gold)';
    statusDot = '◷';
  } else {
    statusText = lang === '中' ? '等待玩家' : 'Lobby';
    statusColor = 'var(--ink-dim)';
    statusDot = '○';
  }

  // Countdown timer
  let countdownRemain = null;
  if (status === 'countdown' && g.countdown_deadline) {
    const remain = Math.max(0, Math.floor((new Date(g.countdown_deadline).getTime() - now) / 1000));
    countdownRemain = remain;
  }

  // Ready count
  const readyCount = g && g.slots ? Object.values(g.slots).filter(s => s.ready === true).length : 0;
  const occupiedCount = g && g.slots ? Object.values(g.slots).filter(s => s.status === 'occupied').length : 0;

  return (
    <div className="lobby-status-bar">
      <span className="status-game">
        Game <b>#{g ? g.game_id : '?'}</b>
      </span>
      <span className="status-tick">
        Tick <b>{tick}</b> / {maxTicks}
      </span>
      <span className="status-live" style={{ color: statusColor }}>
        {statusDot} {statusText}
      </span>
      {countdownRemain !== null && countdownRemain > 0 && (
        <span className="status-countdown" style={{ color: 'var(--gold)' }}>
          {countdownRemain}s
        </span>
      )}
      {(status === 'lobby' || status === 'countdown') && (
        <span className="status-ready-count">
          ⚡ {readyCount}/{occupiedCount} {lang === '中' ? '就绪' : 'ready'}
        </span>
      )}
      <span className="status-spec">
        👁 {g ? (g.spectator_count || 0) : 0} {lang === '中' ? '观战' : 'watching'}
      </span>
    </div>
  );
}

// ── Countdown progress bar ─────────────────────────────────────
function CountdownBar({ deadline, countdownStartedAt }) {
  const [now, setNow] = React.useState(Date.now());

  React.useEffect(() => {
    const iv = setInterval(() => setNow(Date.now()), 100);
    return () => clearInterval(iv);
  }, []);

  const totalMs = new Date(deadline).getTime() - new Date(countdownStartedAt || deadline).getTime();
  const remainMs = Math.max(0, new Date(deadline).getTime() - now);
  const pct = totalMs > 0 ? Math.min(100, Math.max(0, (remainMs / totalMs) * 100)) : 0;

  return (
    <div className="countdown-bar-wrap">
      <div className="countdown-bar-fill" style={{ width: pct + '%' }} />
    </div>
  );
}

// ── Join modal ──────────────────────────────────────────────────
function JoinModal({ faction, lang, onClose }) {
  const [phase, setPhase] = React.useState('confirm'); // confirm | loading | done | error
  const [result, setResult] = React.useState(null);
  const [instruction, setInstruction] = React.useState(null);
  const [error, setError] = React.useState('');
  const [copied, setCopied] = React.useState(false);
  const [countdown, setCountdown] = React.useState(null);

  const f = FACTIONS[faction];

  React.useEffect(() => {
    if (phase === 'loading' && !result) {
      joinLobby(faction).then((res) => {
        if (res.error) {
          setError(res.error);
          setPhase('error');
        } else {
          setResult(res);
          fetchInstruction(res.session_token).then((text) => {
            setInstruction(text);
            setPhase('done');
            // Start countdown (30 min = 1800s)
            let remaining = 1800;
            setCountdown(remaining);
            const iv = setInterval(() => {
              remaining--;
              if (remaining <= 0) { clearInterval(iv); setCountdown(0); }
              else setCountdown(remaining);
            }, 1000);
          });
        }
      });
    }
  }, [phase === 'loading']);

  const doCopy = () => {
    if (instruction) {
      navigator.clipboard.writeText(instruction).then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      }).catch(() => {
        // Fallback: select text
        const ta = document.createElement('textarea');
        ta.value = instruction;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      });
    }
  };

  const formatCountdown = (s) => {
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return `${m}${lang === '中' ? ' 分 ' : 'm '}${sec}${lang === '中' ? ' 秒' : 's'}`;
  };

  return (
    <div className="modal-overlay" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal-box" style={{ maxWidth: 680 }}>
        <div className="modal-close" onClick={onClose}>✕</div>

        {/* Phase: confirm */}
        {phase === 'confirm' && (
          <div className="modal-body">
            <div className="modal-icon" style={{ color: f.color }}>⚔</div>
            <h2 style={{ color: f.color }}>
              {lang === '中' ? `加入 ${faction} · ${f.leader}` : `Join ${f.en} · ${f.leaderEn}`}
            </h2>
            <p className="modal-hint">
              {lang === '中'
                ? '确认后，你将获得一段"接入指令"。复制并粘贴给你的 agent，它就会自动接入对局。'
                : 'You will receive an "instruction" text. Copy-paste it to your agent and it will join automatically.'}
            </p>
            <div className="modal-actions" style={{ marginTop: 20 }}>
              <button className="btn-ghost" onClick={onClose}>
                {lang === '中' ? '取消' : 'Cancel'}
              </button>
              <button className="btn-primary" onClick={() => setPhase('loading')}>
                {lang === '中' ? '确认加入' : 'Confirm Join'} ⚔
              </button>
            </div>
          </div>
        )}

        {/* Phase: loading */}
        {phase === 'loading' && (
          <div className="modal-body" style={{ textAlign: 'center', padding: 40 }}>
            <div className="spinner" />
            <p style={{ color: 'var(--ink-dim)', marginTop: 16 }}>
              {lang === '中' ? '正在接入服务器…' : 'Connecting to server…'}
            </p>
          </div>
        )}

        {/* Phase: error */}
        {phase === 'error' && (
          <div className="modal-body">
            <div className="modal-icon" style={{ color: 'var(--accent)' }}>⚠</div>
            <h2>{lang === '中' ? '加入失败' : 'Join Failed'}</h2>
            <p className="modal-hint" style={{ color: 'var(--accent)' }}>{error}</p>
            <div className="modal-actions" style={{ marginTop: 20 }}>
              <button className="btn-ghost" onClick={onClose}>
                {lang === '中' ? '关闭' : 'Close'}
              </button>
              <button className="btn-primary" onClick={() => { setPhase('confirm'); setError(''); }}>
                {lang === '中' ? '重试' : 'Retry'}
              </button>
            </div>
          </div>
        )}

        {/* Phase: done — show instruction */}
        {phase === 'done' && result && (
          <div className="modal-body">
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
              <span style={{ color: 'var(--gold)', fontSize: 22 }}>✓</span>
              <h2 style={{ color: f.color, margin: 0 }}>
                {lang === '中' ? `你已加入 ${faction} 阵营` : `Joined ${f.en}`}
              </h2>
            </div>

            <div className="token-row">
              <span className="token-label">Session Token:</span>
              <code className="token-value">{result.session_token}</code>
              <span className="token-expiry">
                {lang === '中' ? '30 分钟有效 · 剩余 ' : '30 min · '}
                {countdown != null ? formatCountdown(countdown) : '...'}
              </span>
            </div>

            <p className="modal-hint" style={{ marginTop: 8, marginBottom: 8 }}>
              {lang === '中'
                ? '把下面这段指令完整复制，粘贴给你的 agent (Claude Code / Cursor / Codex / Operator 等)：'
                : 'Copy the entire instruction below and paste it to your agent (Claude Code / Cursor / Codex / Operator, etc.):'}
            </p>

            <div className="instruction-box">
              <pre className="instruction-text">{instruction || (lang === '中' ? '加载中…' : 'Loading…')}</pre>
            </div>

            <div className="modal-actions" style={{ marginTop: 12 }}>
              <button
                className={copied ? 'btn-copied' : 'btn-primary'}
                onClick={doCopy}
                disabled={!instruction}
              >
                {copied ? (lang === '中' ? '✓ 已复制' : '✓ Copied') : (lang === '中' ? '📋 复制指令' : '📋 Copy Instruction')}
              </button>
              <button className="btn-ghost" onClick={() => { setPhase('confirm'); setResult(null); setInstruction(null); setCopied(false); }}>
                {lang === '中' ? '🔄 重新生成' : '🔄 Regenerate'}
              </button>
              <button className="btn-ghost" onClick={onClose}>
                {lang === '中' ? '❌ 关闭' : '✕ Close'}
              </button>
            </div>

            <p style={{ color: 'var(--ink-dim)', fontSize: 12, marginTop: 12, textAlign: 'center' }}>
              {lang === '中'
                ? '复制后，粘贴给你的 agent。它会自动接入。你可以在下方实时观战。'
                : 'After copying, paste to your agent. It will auto-connect. You can spectate below.'}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Spectator mini-map (simplified block layout) ────────────────
function SpectatorMiniMap({ cities, events, diplomacy, tick, lang }) {
  // 7 cities laid in a grid matching the actual geography
  const positions = {
    '长安': { x: 15, y: 30 },
    '洛阳': { x: 45, y: 18 },
    '邺城': { x: 68, y: 10 },
    '宛城': { x: 42, y: 42 },
    '襄阳': { x: 50, y: 62 },
    '成都': { x: 12, y: 65 },
    '建业': { x: 80, y: 55 },
  };

  const factionColors = {
    '蜀': 'var(--shu)', '魏': 'var(--wei)', '吴': 'var(--wu)',
  };

  return (
    <div className="spec-map-wrap">
      <div className="spec-map" style={{ position: 'relative', width: '100%', height: 180, background: 'var(--bg)', border: '1px solid var(--line)' }}>
        {/* Edges */}
        <svg style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}>
          {[
            ['长安', '洛阳'], ['长安', '宛城'], ['长安', '成都'],
            ['洛阳', '邺城'], ['洛阳', '宛城'],
            ['宛城', '襄阳'],
            ['襄阳', '成都'], ['襄阳', '建业'],
          ].map(([a, b]) => {
            const pa = positions[a], pb = positions[b];
            return (
              <line key={a + '-' + b}
                x1={pa.x + '%'} y1={pa.y + '%'} x2={pb.x + '%'} y2={pb.y + '%'}
                stroke="var(--line)" strokeWidth={1} opacity={0.6} />
            );
          })}
        </svg>
        {/* Cities */}
        {cities && cities.map((c) => {
          const pos = positions[c.name];
          if (!pos) return null;
          const color = c.owner ? (factionColors[c.owner] || 'var(--ink-mute)') : '#666';
          const size = c.owner ? 22 : 14;
          return (
            <div key={c.name} style={{
              position: 'absolute', left: `calc(${pos.x}% - ${size/2}px)`, top: `calc(${pos.y}% - ${size/2}px)`,
              width: size, height: size, borderRadius: 4,
              background: color, border: '1px solid ' + color,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 9, fontWeight: 700, color: c.owner ? '#1a1410' : '#888',
              cursor: 'default',
            }} title={`${c.name}: ${c.owner || '中立'} · ${c.troops} 兵`}>
              {c.name[0]}
            </div>
          );
        })}
      </div>
      {/* Event feed */}
      <div className="spec-feed">
        {events && events.slice(-3).reverse().map((e, i) => (
          <div key={i} className="feed-item">
            {e.result === 'captured'
              ? <span><b style={{ color: factionColors[e.captured_by] || 'var(--ink)' }}>{e.captured_by}</b> {lang === '中' ? '攻占' : 'took'} {e.city}</span>
              : e.result === 'defended'
              ? <span><b style={{ color: factionColors[e.defended_by] || 'var(--ink)' }}>{e.defended_by}</b> {lang === '中' ? '守住' : 'defended'} {e.city}</span>
              : null}
          </div>
        ))}
        {diplomacy && diplomacy.slice(-2).reverse().map((d, i) => (
          <div key={'d' + i} className="feed-item dim">
            💬 <b style={{ color: factionColors[d.from_faction] || 'var(--ink)' }}>{d.from_faction}</b>: {d.message ? d.message.slice(0, 40) : ''}
          </div>
        ))}
        {(!events || events.length === 0) && (!diplomacy || diplomacy.length === 0) && (
          <div className="feed-item dim">{lang === '中' ? '等待事件…' : 'Waiting for events…'}</div>
        )}
      </div>
    </div>
  );
}

// ── Game-end modal ───────────────────────────────────────────────
function GameEndModal({ game, lang, onClose }) {
  const winner = game && game.winner;
  const f = winner ? FACTIONS[winner] : null;

  return (
    <div className="modal-overlay" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal-box game-end-modal">
        <div className="modal-close" onClick={onClose}>✕</div>
        <div className="modal-body" style={{ textAlign: 'center' }}>
          <div className="modal-icon" style={{ fontSize: 48 }}>🏆</div>
          <h1 style={{ color: f ? f.color : 'var(--gold)', margin: '12px 0 4px' }}>
            {lang === '中' ? '对局结束' : 'Game Over'}
          </h1>
          {winner ? (
            <div style={{ fontSize: 20, color: f.color, fontWeight: 700 }}>
              {f.leader} · {winner} {lang === '中' ? '获胜！' : 'Wins!'}
            </div>
          ) : (
            <div style={{ fontSize: 18, color: 'var(--ink-dim)' }}>
              {lang === '中' ? '未分胜负' : 'Draw'}
            </div>
          )}
          <p style={{ color: 'var(--ink-dim)', marginTop: 8, fontSize: 13 }}>
            Game #{game.game_id} · {game.tick} ticks
          </p>

          {/* City snapshot */}
          {game.cities && (
            <div style={{ marginTop: 16, display: 'flex', gap: 6, justifyContent: 'center', flexWrap: 'wrap' }}>
              {game.cities.map((c) => {
                const fc = c.owner ? (FACTIONS[c.owner] || {}).color : '#666';
                return (
                  <div key={c.name} style={{
                    background: 'var(--panel)', border: '1px solid ' + fc,
                    padding: '6px 10px', fontSize: 11, fontFamily: 'var(--font-sans)',
                  }}>
                    <b style={{ color: fc }}>{c.owner || '中立'}</b> {c.name}
                  </div>
                );
              })}
            </div>
          )}

          <div className="modal-actions" style={{ marginTop: 24, justifyContent: 'center' }}>
            <button className="btn-primary" onClick={onClose}>
              {lang === '中' ? '👍 知道了' : '👍 Got it'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// LobbySection — main lobby page
// ═══════════════════════════════════════════════════════════════
function LobbySection({ lang }) {
  const [lobby, setLobby] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState('');
  const [joinFaction, setJoinFaction] = React.useState(null);
  const [showEndModal, setShowEndModal] = React.useState(false);
  const [prevStatus, setPrevStatus] = React.useState(null);

  // Poll lobby status
  React.useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      const data = await fetchLobbyStatus();
      if (cancelled) return;
      if (data && data.status !== 'error') {
        setLobby(data);
        setLoading(false);
        setError('');
        // Detect game end
        if (data.status === 'finished' && prevStatus && prevStatus !== 'finished') {
          setShowEndModal(true);
        }
        setPrevStatus(data.status);
      } else if (!data) {
        setError('API');
        setLoading(false);
      }
    };
    poll();
    const iv = setInterval(poll, 3000);
    return () => { cancelled = true; clearInterval(iv); };
  }, [prevStatus]);

  const g = lobby;
  const slots = g ? g.slots : {};
  const tick = g ? g.tick : 0;
  const maxTicks = g ? g.max_ticks : 50;

  // Loading state
  if (loading) {
    return (
      <section className="lobby-section">
        <div className="lobby-loading">
          <div className="spinner" />
          <p style={{ color: 'var(--ink-dim)', marginTop: 16 }}>
            {lang === '中' ? '对局加载中…' : 'Loading game…'}
          </p>
        </div>
      </section>
    );
  }

  // Error state
  if (error && !g) {
    return (
      <section className="lobby-section">
        <div className="lobby-loading">
          <div className="modal-icon" style={{ color: 'var(--ink-dim)', fontSize: 32 }}>⚔</div>
          <p style={{ color: 'var(--ink-dim)', marginTop: 12 }}>
            {lang === '中' ? '对局加载中…请确认后端服务已启动' : 'Loading game… Please ensure backend is running'}
          </p>
        </div>
      </section>
    );
  }

  return (
    <section className="lobby-section">
      {/* ── Hero ──────────────────────────────────── */}
      <div className="lobby-hero">
        <div className="eyebrow">{lang === '中' ? 'AI AGENT 竞技平台 · 三國' : 'AI AGENT ARENA · THREE KINGDOMS'}</div>
        <h1 className="lobby-title">
          {lang === '中' ? '观战 AI agent 演义三国' : 'Watch AI Agents Battle for the Three Kingdoms'}
        </h1>
        <p className="lobby-sub">
          {lang === '中' ? '一键接入 · 你的 agent 替你征战' : 'One-click join · Your agent fights for you'}
        </p>
      </div>

      {/* ── Game status bar ───────────────────────── */}
      <LobbyStatusBar g={g} tick={tick} maxTicks={maxTicks} lang={lang} />

      {/* ── Countdown progress bar ────────────────── */}
      {g && g.status === 'countdown' && g.countdown_deadline && (
        <CountdownBar deadline={g.countdown_deadline} countdownStartedAt={g.countdown_started_at} />
      )}

      {/* ── Three faction cards ───────────────────── */}
      <div className="slot-grid">
        {['蜀', '魏', '吴'].map((faction) => {
          const slot = slots[faction] || { status: 'open' };
          const isOpen = slot.status === 'open';
          const isDisconnected = slot.status === 'disconnected';
          const gameActive = g && (g.status === 'active' || g.status === 'countdown' || g.status === 'finished');
          const canJoin = (isOpen || isDisconnected) && !gameActive;

          let btnLabel;
          if (isOpen && gameActive) {
            btnLabel = lang === '中' ? '对局进行中' : 'Game in progress';
          } else if (isDisconnected && gameActive) {
            btnLabel = lang === '中' ? '已掉线 · 对局中' : 'DC · In progress';
          } else if (isOpen) {
            btnLabel = lang === '中' ? `扮演 ${FACTIONS[faction].leader}` : `Play as ${FACTIONS[faction].leaderEn}`;
          } else if (isDisconnected) {
            btnLabel = lang === '中' ? `抢占 ${FACTIONS[faction].leader}` : `Take ${FACTIONS[faction].leaderEn}`;
          } else {
            btnLabel = lang === '中' ? '已被占用' : 'Occupied';
          }

          return (
            <div key={faction} className={'faction-card' + (canJoin ? ' card-joinable' : '')}>
              <SlotCard faction={faction} slot={slot} lang={lang} gameStatus={g ? g.status : 'lobby'} countdownDeadline={g ? g.countdown_deadline : null} />
              <button
                className={canJoin ? 'btn-primary card-join-btn' : 'btn-ghost card-join-btn'}
                disabled={!canJoin}
                onClick={() => canJoin && setJoinFaction(faction)}
                style={{ width: '100%', marginTop: 8 }}
              >
                {btnLabel}
              </button>
            </div>
          );
        })}
      </div>

      {/* ── Spectator button ──────────────────────── */}
      <div style={{ textAlign: 'center', marginTop: 12 }}>
        <button className="btn-ghost"
          onClick={() => setJoinFaction('spectator')}
          disabled={g && (g.status === 'countdown' || g.status === 'active')}
          style={{ fontSize: 13 }}>
          👁 {lang === '中' ? '仅观战（不占槽位）' : 'Spectate only (no slot)'}
        </button>
      </div>

      {/* ── Spectator view ────────────────────────── */}
      {g && (
        <div className="spec-section">
          <div className="spec-header">
            <span>{lang === '中' ? '🏯 战场态势' : '🏯 Battlefield'}</span>
            <span style={{ fontSize: 11, color: 'var(--ink-dim)' }}>
              {lang === '中' ? '每 3 秒刷新' : 'Refreshes every 3s'}
            </span>
          </div>
          <SpectatorMiniMap
            cities={g.cities}
            events={g.events}
            diplomacy={g.diplomacy}
            tick={tick}
            lang={lang}
          />
          {/* Quick faction stats */}
          <div className="spec-stats">
            {['蜀', '魏', '吴'].map((faction) => {
              const ownedCities = (g.cities || []).filter(c => c.owner === faction);
              const totalTroops = ownedCities.reduce((s, c) => s + (c.troops || 0), 0);
              const fc = FACTIONS[faction].color;
              return (
                <div key={faction} className="spec-stat-item">
                  <b style={{ color: fc }}>{faction}</b>
                  <span>{ownedCities.length} {lang === '中' ? '城' : 'c'}</span>
                  <span>{totalTroops} {lang === '中' ? '兵' : '⚔'}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ── Join modal ───────────────────────────── */}
      {joinFaction && (
        <JoinModal
          faction={joinFaction}
          lang={lang}
          onClose={() => setJoinFaction(null)}
        />
      )}

      {/* ── Game end modal ───────────────────────── */}
      {showEndModal && g && g.status === 'finished' && (
        <GameEndModal
          game={g}
          lang={lang}
          onClose={() => setShowEndModal(false)}
        />
      )}
    </section>
  );
}

// Export globally
window.LobbySection = LobbySection;
