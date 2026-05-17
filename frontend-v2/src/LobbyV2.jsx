import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import usePolling from './hooks/usePolling'

const FACTIONS = ['蜀', '魏', '吴']
const FACTION_COLORS = {
  蜀: 'var(--shu)',
  魏: 'var(--wei)',
  吴: 'var(--wu)',
}
const FACTION_MONARCHS = { 蜀: '刘备', 魏: '曹操', 吴: '孙权' }

// ── Slot status → display ──────────────────────────
function slotUI(slot, faction, gameStatus) {
  const s = slot?.status || 'open'
  const ready = slot?.ready || false

  // Countdown / in-progress → locked
  if (gameStatus === 'countdown' || gameStatus === 'active' || gameStatus === 'in_progress') {
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
        description: `断开 ${slot?.disconnected_sec || '?'}s · 剩余 ${slot?.reconnect_remaining_sec || '?'}s 可重连`,
        canAct: false,
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
  const { data, error, loading } = usePolling('/v1/lobby/status', 3000)
  const [localSlots, setLocalSlots] = useState(null)
  const [msg, setMsg] = useState(null)
  const msgTimer = useRef(null)

  // Merge polling data with optimistic local updates
  const slots = localSlots || data?.slots
  const gameStatus = data?.status
  const gameId = data?.game_id
  const tick = data?.tick
  const maxTicks = data?.max_ticks
  const countdownDeadline = data?.countdown_deadline

  // Clear local overrides when server data changes
  useEffect(() => {
    setLocalSlots(null)
  }, [data?.slots])

  function flash(msgText) {
    setMsg(msgText)
    clearTimeout(msgTimer.current)
    msgTimer.current = setTimeout(() => setMsg(null), 5000)
  }

  if (loading && !data) {
    return <div className="page"><p>加载中…</p></div>
  }

  if (error) {
    console.error('LobbyV2 fetch error:', error)
  }

  console.log('LobbyV2 poll:', {
    game_id: gameId,
    status: gameStatus,
    tick,
    slot_states: slots,
  })

  // ── Actions ─────────────────────────────────────
  async function actJoin(faction) {
    flash(null)
    try {
      const res = await fetch('/v1/lobby/join', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ faction }),
      })
      const body = await res.json()
      if (!res.ok) {
        if (body.error_code === 'COUNTDOWN_STARTED') {
          flash('倒计时已启动，无法加入')
        } else {
          flash(`加入失败: ${body.detail || body.error_code}`)
        }
        return
      }
      // Optimistic update
      setLocalSlots(prev => ({
        ...(prev || slots),
        [faction]: { status: 'occupied', ready: false, agent_display_name: '你', ip: '***' },
      }))
      flash(`已加入 ${faction}`)
    } catch (e) {
      flash(`网络错误: ${e.message}`)
    }
  }

  async function actAssignAI(faction) {
    flash(null)
    try {
      const res = await fetch('/v1/lobby/assign-ai', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ faction }),
      })
      const body = await res.json()
      if (!res.ok) {
        flash(`配 AI 失败: ${body.detail}`)
        return
      }
      setLocalSlots(prev => ({
        ...(prev || slots),
        [faction]: { status: 'ai_managed', ready: true, agent_display_name: `托管AI-${faction}` },
      }))
      flash(`已配 ${faction} 为 AI 托管`)
    } catch (e) {
      flash(`网络错误: ${e.message}`)
    }
  }

  async function actReleaseAI(faction) {
    flash(null)
    try {
      const res = await fetch('/v1/lobby/release-ai', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ faction }),
      })
      const body = await res.json()
      if (!res.ok) {
        flash(`释放失败: ${body.detail}`)
        return
      }
      setLocalSlots(prev => ({
        ...(prev || slots),
        [faction]: { status: 'open', ready: false },
      }))
      flash(`已释放 ${faction} AI 托管`)
    } catch (e) {
      flash(`网络错误: ${e.message}`)
    }
  }

  async function actReady(faction, token) {
    flash(null)
    try {
      const res = await fetch('/v1/lobby/ready', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token }),
      })
      if (!res.ok) {
        const body = await res.json()
        flash(`Ready 失败: ${body.detail}`)
        return
      }
      setLocalSlots(prev => ({
        ...(prev || slots),
        [faction]: { ...((prev || slots)[faction]), ready: true },
      }))
      flash('已就绪')
    } catch (e) {
      flash(`网络错误: ${e.message}`)
    }
  }

  // ── Render ───────────────────────────────────────
  return (
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
                  该位置玩家掉线，{slot.reconnect_remaining_sec} 秒后自动释放给托管 AI
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
  )
}
