import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import usePolling from './hooks/usePolling'
import { api } from './api'
import { FACTIONS, FACTION_COLORS, FACTION_MONARCHS, isGameInProgress } from './constants'

// ── Helpers ────────────────────────────────────────
function fmtDuration(sec) {
  if (sec == null || isNaN(sec)) return '?'
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return m > 0 ? `${m}m${s}s` : `${s}s`
}

// ── Slot status → display ──────────────────────────
function slotUI(slot, faction, gameStatus) {
  const s = slot?.status || 'open'
  const ready = slot?.ready || false

  // Countdown / in-progress → locked
  if (gameStatus === 'countdown' || isGameInProgress(gameStatus)) {
    return {
      label: gameStatus === 'countdown' ? '倒计时中' : '对局中',
      cssClass: 'locked',
      description: `${FACTION_MONARCHS[faction]} · ${slot?.agent_display_name || '—'}`,
      canAct: false,
    }
  }

  // Finished → show result
  if (gameStatus === 'finished') {
    return {
      label: '已结束',
      cssClass: 'finished',
      description: '',
      canAct: false,
    }
  }

  switch (s) {
    case 'open':
      return {
        label: '空缺',
        cssClass: 'open',
        description: `${faction} · ${FACTION_MONARCHS[faction]}`,
        canAct: true,
        actions: ['assign_ai', 'join'],
      }
    case 'ai_managed':
      return {
        label: 'AI 托管',
        cssClass: 'ai',
        description: slot?.agent_display_name || 'Managed AI',
        canAct: true,
        actions: ['grab', 'release_ai'],
      }
    case 'occupied':
      return ready
        ? {
            label: '已就绪',
            cssClass: 'ready',
            description: `${slot?.agent_display_name || ''} · IP ${slot?.ip || '***'}`,
            canAct: false,
          }
        : {
            label: '未就绪',
            cssClass: 'occupied',
            description: `${slot?.agent_display_name || ''} · IP ${slot?.ip || '***'}`,
            canAct: true,
            actions: ['ready'],
          }
    case 'disconnected':
      return {
        label: '掉线',
        cssClass: 'disconnected',
        description: `已断开 ${fmtDuration(slot?.disconnected_sec)}`,
        canAct: true,
        actions: ['grab'],
      }
    default:
      return { label: s, cssClass: '', description: '', canAct: false }
  }
}

// ── Countdown overlay ──────────────────────────────
function CountdownOverlay({ deadline }) {
  const [sec, setSec] = useState(5)

  useEffect(() => {
    if (!deadline) return
    const tick = () => {
      const remaining = Math.max(0, Math.ceil((new Date(deadline).getTime() - Date.now()) / 1000))
      setSec(remaining)
    }
    tick()
    const timer = setInterval(tick, 200)
    return () => clearInterval(timer)
  }, [deadline])

  if (sec <= 0) return null

  return (
    <div className="countdown-overlay">
      <div className="countdown-number">{sec}</div>
      <div className="countdown-label">倒计时</div>
    </div>
  )
}

// ── Main component ─────────────────────────────────
export default function LobbyV2() {
  const navigate = useNavigate()
  const [pollInterval, setPollInterval] = useState(3000)
  const { data, error, isLoading } = usePolling('/v1/lobby/status', { intervalMs: pollInterval })
  const [localSlots, setLocalSlots] = useState(null)
  const [msg, setMsg] = useState(null)
  const msgTimer = useRef(null)
  const pendingRef = useRef(null) // { faction, check: (slot) => boolean, until: number }

  // Adapt polling interval to game status
  useEffect(() => {
    if (!data?.status) return
    const next = data.status === 'finished' ? null
      : data.status === 'countdown' ? 1000
      : data.status === 'lobby' ? 5000
      : 3000
    setPollInterval(prev => prev === next ? prev : next)
  }, [data?.status])

  // Merge polling data with optimistic local updates
  const slots = localSlots || data?.slots
  const gameStatus = data?.status
  const gameId = data?.game_id
  const winner = data?.winner
  const tick = data?.tick
  const maxTicks = data?.max_ticks
  const countdownDeadline = data?.countdown_deadline

  // Smart reconciliation: only clear optimistic state when server confirms or timeout
  useEffect(() => {
    const pending = pendingRef.current
    if (!pending) { setLocalSlots(null); return }

    const serverSlot = data?.slots?.[pending.faction]
    if (serverSlot && pending.check(serverSlot)) {
      setLocalSlots(null)
      pendingRef.current = null
    } else if (Date.now() > pending.until) {
      setLocalSlots(null)
      pendingRef.current = null
    }
  }, [data?.slots])

  function flash(msgText) {
    setMsg(msgText)
    clearTimeout(msgTimer.current)
    msgTimer.current = setTimeout(() => setMsg(null), 5000)
  }

  if (isLoading && !data) {
    return <div className="page"><p>加载中…</p></div>
  }

  if (error) {
    console.error('LobbyV2 fetch error:', error)
  }

  function _revertSlot(faction) {
    setLocalSlots(prev => {
      if (!prev) return prev
      const next = { ...prev }
      delete next[faction]
      return next
    })
  }

  // ── Actions ─────────────────────────────────────
  async function actJoin(faction) {
    flash(null)
    pendingRef.current = { faction, check: s => s.status === 'occupied', until: Date.now() + 5000 }
    setLocalSlots(prev => ({
      ...(prev || slots),
      [faction]: { status: 'occupied', ready: false, agent_display_name: '你', ip: '***' },
    }))
    try {
      await api.joinLobby(faction)
      flash(`已加入 ${faction}`)
    } catch (e) {
      _revertSlot(faction)
      pendingRef.current = null
      if (e.code === 'COUNTDOWN_STARTED') {
        flash('倒计时已启动，无法加入')
      } else {
        flash(`加入失败: ${e.message}`)
      }
    }
  }

  async function actAssignAI(faction) {
    flash(null)
    pendingRef.current = { faction, check: s => s.status === 'ai_managed', until: Date.now() + 5000 }
    setLocalSlots(prev => ({
      ...(prev || slots),
      [faction]: { status: 'ai_managed', ready: true, agent_display_name: `托管AI-${faction}` },
    }))
    try {
      await api.assignAI(faction)
      flash(`已配 ${faction} 为 AI 托管`)
    } catch (e) {
      _revertSlot(faction)
      pendingRef.current = null
      flash(`配 AI 失败: ${e.message}`)
    }
  }

  async function actReleaseAI(faction) {
    flash(null)
    pendingRef.current = { faction, check: s => s.status === 'open', until: Date.now() + 5000 }
    setLocalSlots(prev => ({
      ...(prev || slots),
      [faction]: { status: 'open', ready: false },
    }))
    try {
      await api.releaseAI(faction)
      flash(`已释放 ${faction} AI 托管`)
    } catch (e) {
      _revertSlot(faction)
      pendingRef.current = null
      flash(`释放失败: ${e.message}`)
    }
  }

  async function actReady(faction, token) {
    flash(null)
    pendingRef.current = { faction, check: s => s.ready === true, until: Date.now() + 5000 }
    setLocalSlots(prev => ({
      ...(prev || slots),
      [faction]: { ...((prev || slots)[faction]), ready: true },
    }))
    try {
      await api.ready(token)
      flash('已就绪')
    } catch (e) {
      _revertSlot(faction)
      pendingRef.current = null
      flash(`Ready 失败: ${e.message}`)
    }
  }

  // ── Render ───────────────────────────────────────
  return (
    <div className="theme-dark" style={{ minHeight: '100vh' }}>
    <div className="page lobby-page">
      {error && (
        <div className="error-banner">Failed to fetch: {error}</div>
      )}

      {/* ── Header ─────────────────────────────── */}
      <div className="lobby-header">
        <div className="lobby-title-row">
          <h1>三国 Arena</h1>
          <span className="lobby-nav">
            <span className={`status-tag status-${gameStatus}`}>{gameStatus}</span>
          </span>
        </div>
        <div className="lobby-meta">
          Game <span className="game-id">#{gameId ?? '?'}</span>
          {' · '}Tick {tick ?? '?'}/{maxTicks ?? '?'}
          {data?.spectator_count > 0 && <> · {data.spectator_count} 观战中</>}
        </div>
      </div>

      {msg && <div className="msg-banner">{msg}</div>}

      {/* ── Finished result ─────────────────────── */}
      {gameStatus === 'finished' && winner && (
        <div className="finished-banner">
          胜方: <span style={{ color: FACTION_COLORS[winner] || 'var(--gold)', fontWeight: 700 }}>
            {winner} · {FACTION_MONARCHS[winner]}
          </span>
          {' · '}
          <a href={`/v2/spectate?game=${gameId}`} style={{ color: 'var(--gold)' }}>
            查看战报与评书 →
          </a>
        </div>
      )}

      {/* ── Countdown overlay ──────────────────── */}
      {gameStatus === 'countdown' && countdownDeadline && (
        <CountdownOverlay deadline={countdownDeadline} />
      )}

      {/* ── Slot cards ─────────────────────────── */}
      <div className="slot-row">
        {FACTIONS.map((f) => {
          const slot = slots?.[f]
          const ui = slotUI(slot, f, gameStatus)

          return (
            <div
              key={f}
              className={`slot-card slot-${ui.cssClass}`}
              style={{ borderColor: FACTION_COLORS[f] }}
            >
              <div className="slot-faction" style={{ color: FACTION_COLORS[f] }}>
                {f}
                <span className="slot-monarch"> · {FACTION_MONARCHS[f]}</span>
              </div>

              <div className="slot-status-label">{ui.label}</div>
              <div className="slot-desc">{ui.description}</div>

              {ui.canAct && (
                <div className="slot-buttons">
                  {ui.actions?.includes('assign_ai') && (
                    <button className="btn-sm btn-ai" onClick={() => actAssignAI(f)}>
                      配 AI 托管
                    </button>
                  )}
                  {ui.actions?.includes('join') && (
                    <button className="btn-sm btn-join" onClick={() => actJoin(f)}>
                      加入 {f}
                    </button>
                  )}
                  {ui.actions?.includes('grab') && gameStatus !== 'countdown' && (
                    <button className="btn-sm btn-grab" onClick={() => actJoin(f)}>
                      抢占 {f}
                    </button>
                  )}
                  {ui.actions?.includes('release_ai') && (
                    <button className="btn-sm btn-release" onClick={() => actReleaseAI(f)}>
                      释放 AI
                    </button>
                  )}
                  {ui.actions?.includes('ready') && (
                    <span className="slot-need-ready">等待 Ready</span>
                  )}
                </div>
              )}

              {/* Disconnected slot: show reconnect countdown */}
              {slot?.status === 'disconnected' && slot?.reconnect_remaining_sec > 0 && (
                <div className="slot-reconnect-info">
                  该位置玩家掉线，{fmtDuration(slot.reconnect_remaining_sec)} 后自动释放给托管 AI（也可立即点击抢占）
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* ── Spectator-only button ──────────────── */}
      <div className="lobby-footer">
        <button
          className="btn-spectate"
          onClick={() => navigate(`/spectate?game=${gameId}`)}
        >
          仅观战（不占槽位）
        </button>
      </div>
    </div>
    </div>
  )
}
