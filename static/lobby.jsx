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
  const isSpectator = !f;

  React.useEffect(() => {
    if (phase === 'loading' && !result) {
      joinLobby(faction).then((res) => {
        if (res.error) {
          setError(res.error);
          setPhase('error');
        } else {
          setResult(res);
          if (isSpectator) {
            setPhase('done');
          } else {
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
        {phase === 'confirm' && !isSpectator && (
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

        {/* Phase: confirm — spectator */}
        {phase === 'confirm' && isSpectator && (
          <div className="modal-body">
            <div className="modal-icon" style={{ color: 'var(--ink-dim)', fontSize: 40 }}>👁</div>
            <h2 style={{ color: 'var(--ink)' }}>
              {lang === '中' ? '观战模式' : 'Spectator Mode'}
            </h2>
            <p className="modal-hint">
              {lang === '中'
                ? '你可以观看战场态势和实时事件，无需占用阵营槽位。'
                : 'Watch the battlefield and live events without occupying a faction slot.'}
            </p>
            <div className="modal-actions" style={{ marginTop: 20 }}>
              <button className="btn-ghost" onClick={onClose}>
                {lang === '中' ? '取消' : 'Cancel'}
              </button>
              <button className="btn-primary" onClick={() => setPhase('loading')}>
                👁 {lang === '中' ? '开始观战' : 'Start Watching'}
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

        {/* Phase: done — show instruction (faction join) */}
        {phase === 'done' && result && !isSpectator && (
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

        {/* Phase: done — spectator */}
        {phase === 'done' && result && isSpectator && (
          <div className="modal-body" style={{ textAlign: 'center' }}>
            <div style={{ color: 'var(--gold)', fontSize: 40, marginBottom: 8 }}>👁</div>
            <h2 style={{ color: 'var(--ink)', margin: '0 0 8px' }}>
              {lang === '中' ? '正在观战中' : 'Now Watching'}
            </h2>
            <p className="modal-hint">
              {lang === '中'
                ? '你已接入观战。战场态势会实时刷新。'
                : 'You are now spectating. The battlefield will update in real time.'}
            </p>
            <div className="modal-actions" style={{ marginTop: 20, justifyContent: 'center' }}>
              <button className="btn-primary" onClick={onClose}>
                {lang === '中' ? '关闭 · 开始观战' : 'Close · Watch'}
              </button>
            </div>
          </div>
        )}

      </div>
    </div>
  );
}

// ── Spectator mini-map (upgraded) ─────────────────────────────
function SpectatorMiniMap({ cities, events, diplomacy, tick, lang, onEventClick }) {
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

  const cityList = cities || [];
  const eventList = events || [];
  const diplomacyList = diplomacy || [];

  return (
    <div className="spec-map-wrap">
      <div className="spec-map">
        <svg className="spec-map-roads" viewBox="0 0 100 100" preserveAspectRatio="none">
          {[
            ['长安', '洛阳'], ['长安', '宛城'], ['长安', '成都'],
            ['洛阳', '邺城'], ['洛阳', '宛城'],
            ['宛城', '襄阳'],
            ['襄阳', '成都'], ['襄阳', '建业'],
          ].map(([a, b]) => {
            const pa = positions[a], pb = positions[b];
            return (
              <line key={a + '-' + b} className="spec-road"
                x1={pa.x} y1={pa.y} x2={pb.x} y2={pb.y} />
            );
          })}
        </svg>
        {cityList.map((c) => {
          const pos = positions[c.name];
          if (!pos) return null;
          const fcClass = c.owner ? ('faction-' + c.owner) : 'neutral';
          const color = c.owner ? (factionColors[c.owner] || 'var(--ink-mute)') : 'var(--ink-mute)';
          return (
            <div key={c.name}
              className={'spec-city ' + fcClass}
              style={{
                left: pos.x + '%', top: pos.y + '%',
                '--city-color': color,
              }}
              title={`${c.name}: ${c.owner || (lang === '中' ? '中立' : 'Neutral')} · ${c.troops} ${lang === '中' ? '兵' : 'troops'}`}
            >
              <span className="spec-city-name">{c.name[0]}</span>
              <span className="spec-city-troops">{c.troops}</span>
            </div>
          );
        })}
      </div>
      <div className="spec-feed">
        {eventList.length > 0
          ? eventList.slice(-10).reverse().map((e, i) => {
              const fc = factionColors[e.captured_by || e.defended_by] || 'var(--ink)';
              const hasNarrative = !!e.dayan_narrative;
              return (
                <div key={i}
                  className={'feed-item' + (hasNarrative ? ' feed-item-clickable' : '')}
                  onClick={() => hasNarrative && onEventClick && onEventClick(e)}
                  title={hasNarrative ? (lang === '中' ? '点击查看大衍战报' : 'Click for battle report') : ''}
                >
                  {e.result === 'captured'
                    ? <span><b style={{ color: fc }}>{e.captured_by}</b> {lang === '中' ? '攻占' : 'took'} {e.city}</span>
                    : e.result === 'defended'
                    ? <span><b style={{ color: fc }}>{e.defended_by}</b> {lang === '中' ? '守住' : 'defended'} {e.city}</span>
                    : null}
                  {hasNarrative && <span className="feed-narrative-hint"> 📜</span>}
                </div>
              );
            })
          : <div className="feed-item dim">{lang === '中' ? '等待事件…' : 'Waiting…'}</div>
        }
        {diplomacyList.slice(-5).reverse().map((d, i) => (
          <div key={'d' + i} className="feed-item feed-diplomacy">
            💬 <b style={{ color: factionColors[d.from_faction] || 'var(--ink)' }}>{d.from_faction}</b>: {d.message ? d.message.slice(0, 50) : ''}
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Tick progress bar ──────────────────────────────────────────
function TickProgressBar({ tickStartedAt, tickTimeoutSec, lang }) {
  const [now, setNow] = React.useState(Date.now());

  React.useEffect(() => {
    const iv = setInterval(() => setNow(Date.now()), 100);
    return () => clearInterval(iv);
  }, []);

  if (!tickStartedAt) return null;

  const elapsedMs = now - new Date(tickStartedAt).getTime();
  const timeoutMs = (tickTimeoutSec || 60) * 1000;
  const pct = Math.min(100, Math.max(0, (elapsedMs / timeoutMs) * 100));
  const remainSec = Math.max(0, Math.floor((timeoutMs - elapsedMs) / 1000));
  const isUrgent = remainSec <= 10;

  return (
    <div className="tick-progress-wrap">
      <div className={'tick-progress-bar' + (isUrgent ? ' urgent' : '')}
        style={{ width: pct + '%' }} />
      <span className="tick-progress-label">
        {remainSec}s {lang === '中' ? '剩余' : 'left'}
      </span>
    </div>
  );
}

// ── Agent status bar ───────────────────────────────────────────
function AgentStatusBar({ agents, lang }) {
  const factionOrder = ['蜀', '魏', '吴'];
  return (
    <div className="agent-status-bar">
      {factionOrder.map(faction => {
        const agent = (agents || []).find(a => a.faction === faction);
        const submitted = agent ? agent.submitted : false;
        const fc = FACTIONS[faction].color;
        return (
          <div key={faction} className={'agent-status-item' + (submitted ? ' submitted' : ' pending')}>
            <span className="agent-status-dot" style={{ color: fc }}>
              {submitted ? '●' : '○'}
            </span>
            <span className="agent-status-label">
              {faction} {submitted ? '✓' : '…'}
            </span>
          </div>
        );
      })}
    </div>
  );
}

// ── Commentary modal ───────────────────────────────────────────
function CommentaryModal({ event, lang, onClose }) {
  if (!event) return null;

  const factionColors = { '蜀': 'var(--shu)', '魏': 'var(--wei)', '吴': 'var(--wu)' };
  const isCaptured = event.result === 'captured';
  const winner = isCaptured ? event.captured_by : event.defended_by;

  return (
    <div className="modal-overlay" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal-box commentary-modal">
        <div className="modal-close" onClick={onClose}>✕</div>
        <div className="modal-body">
          <h3 style={{ color: factionColors[winner] || 'var(--gold)' }}>
            {event.city} · {isCaptured
              ? (lang === '中' ? `${event.captured_by} 攻占` : `${event.captured_by} captured`)
              : (lang === '中' ? `${event.defended_by} 守住` : `${event.defended_by} defended`)}
          </h3>

          {event.dayan_hexagram && (
            <div className="commentary-hexagrams">
              <span>{lang === '中' ? '主卦' : 'Main'}: {event.dayan_hexagram.main}</span>
              <span>{lang === '中' ? '变卦' : 'Changed'}: {event.dayan_hexagram.changed}</span>
            </div>
          )}

          {event.dayan_narrative && (
            <div className="commentary-narrative">
              <h4>{lang === '中' ? '📜 大衍战报' : '📜 DaYan Battle Report'}</h4>
              <div className="narrative-text">{event.dayan_narrative}</div>
            </div>
          )}

          {event.casualties_attacker != null && (
            <div className="commentary-stats">
              <span>{lang === '中' ? '攻方折损' : 'Atk loss'}: {(event.casualties_attacker * 100).toFixed(0)}%</span>
              <span>{lang === '中' ? '守方折损' : 'Def loss'}: {(event.casualties_defender * 100).toFixed(0)}%</span>
              <span>{lang === '中' ? '天命归属' : 'Destiny'}: {event.dayan_winner === 'attacker'
                ? (lang === '中' ? '攻方' : 'Attacker')
                : (lang === '中' ? '守方' : 'Defender')}</span>
            </div>
          )}
        </div>
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
function LobbySection({ lang, currentGame }) {
  const [lobby, setLobby] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState('');
  const [joinFaction, setJoinFaction] = React.useState(null);
  const [showEndModal, setShowEndModal] = React.useState(false);
  const [prevStatus, setPrevStatus] = React.useState(null);
  const [selectedEvent, setSelectedEvent] = React.useState(null);

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

          {/* Agent submission status — from /current-game */}
          {currentGame && currentGame.agents && g.status === 'active' && (
            <AgentStatusBar agents={currentGame.agents} lang={lang} />
          )}

          {/* Tick progress bar — from /current-game */}
          {g.status === 'active' && currentGame && currentGame.tick_started_at && (
            <TickProgressBar
              tickStartedAt={currentGame.tick_started_at}
              tickTimeoutSec={currentGame.tick_timeout_sec}
              lang={lang}
            />
          )}

          <SpectatorMiniMap
            cities={currentGame && currentGame.cities ? currentGame.cities : g.cities}
            events={currentGame && currentGame.events ? currentGame.events : (g.events || [])}
            diplomacy={currentGame && currentGame.diplomacy ? currentGame.diplomacy : (g.diplomacy || [])}
            tick={tick}
            lang={lang}
            onEventClick={(e) => setSelectedEvent(e)}
          />

          {/* Faction stats — from /current-game if available */}
          <div className="spec-stats">
            {['蜀', '魏', '吴'].map((faction) => {
              const cgFaction = currentGame && currentGame.factions ? currentGame.factions[faction] : null;
              const ownedCities = cgFaction
                ? cgFaction.cities
                : (g.cities || []).filter(c => c.owner === faction).length;
              const totalTroops = cgFaction
                ? cgFaction.troops
                : (g.cities || []).filter(c => c.owner === faction).reduce((s, c) => s + (c.troops || 0), 0);
              const fc = FACTIONS[faction].color;
              return (
                <div key={faction} className="spec-stat-item">
                  <b style={{ color: fc }}>{faction}</b>
                  <span>{ownedCities} {lang === '中' ? '城' : 'c'}</span>
                  <span>{totalTroops} {lang === '中' ? '兵' : '⚔'}</span>
                  {cgFaction && cgFaction.alliance_with && (
                    <span className="spec-alliance">🤝 {cgFaction.alliance_with}</span>
                  )}
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

      {/* ── Commentary modal ──────────────────────── */}
      {selectedEvent && (
        <CommentaryModal
          event={selectedEvent}
          lang={lang}
          onClose={() => setSelectedEvent(null)}
        />
      )}
    </section>
  );
}

// Export globally
window.LobbySection = LobbySection;
