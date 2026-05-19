import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import usePolling from '../hooks/usePolling'
import { api } from '../api'
import { FACTIONS, FACTION_COLORS, FACTION_MONARCHS, isGameInProgress } from '../constants'

// ── Helpers ────────────────────────────────────────
function fmtDuration(sec) {
  if (sec == null || isNaN(sec)) return '?'
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return m > 0 ? `${m}m${s}s` : `${s}s`
}

function slotUI(slot, faction, gameStatus) {
  const s = slot?.status || 'open'
  const ready = slot?.ready || false

  if (gameStatus === 'countdown' || isGameInProgress(gameStatus)) {
    return {
      label: gameStatus === 'countdown' ? '倒计时中' : '对局中',
      cssClass: 'locked',
      description: `${FACTION_MONARCHS[faction]} · ${slot?.agent_display_name || '—'}`,
      canAct: false,
    }
  }

  if (gameStatus === 'finished') {
    return { label: '已结束', cssClass: 'finished', description: '', canAct: false }
  }

  switch (s) {
    case 'open':
      return { label: '空缺', cssClass: 'open', description: `${faction} · ${FACTION_MONARCHS[faction]}`, canAct: true, actions: ['assign_ai', 'join'] }
    case 'ai_managed':
      return { label: 'AI 托管', cssClass: 'ai', description: slot?.agent_display_name || 'Managed AI', canAct: true, actions: ['grab', 'release_ai'] }
    case 'occupied':
      return ready
        ? { label: '已就绪', cssClass: 'ready', description: `${slot?.agent_display_name || ''} · IP ${slot?.ip || '***'}`, canAct: false }
        : { label: '未就绪', cssClass: 'occupied', description: `${slot?.agent_display_name || ''} · IP ${slot?.ip || '***'}`, canAct: true, actions: ['ready'] }
    case 'disconnected':
      return { label: '掉线', cssClass: 'disconnected', description: `已断开 ${fmtDuration(slot?.disconnected_sec)}`, canAct: true, actions: ['grab'] }
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
    <div className="lb-countdown-overlay">
      <div className="lb-countdown-number">{sec}</div>
      <div className="lb-countdown-label">倒计时</div>
    </div>
  )
}

// ── Battle preview (bottom panel) ─────────────────
function BattlePreview({ data }) {
  const navigate = useNavigate()
  if (!data || !isGameInProgress(data.status)) {
    return (
      <div className="lb-battle-preview">
        <div className="lb-bp-placeholder">等待对局开始…</div>
      </div>
    )
  }
  const tick = data.tick ?? 0
  const cities = data.cities || []
  const cityLines = cities.slice(0, 3).map(c =>
    `${c.name}:${c.owner || '中立'} ${c.troops}兵`
  ).join(' · ')

  return (
    <div className="lb-battle-preview">
      <div className="lb-bp-title">战场态势</div>
      <div className="lb-bp-summary">
        Tick {tick}/{data.max_ticks ?? 50} · {cityLines}
        {cities.length > 3 && ` · …共${cities.length}城`}
      </div>
      <button className="btn-primary" style={{ marginTop: 12 }}
        onClick={() => navigate(`/spectate?game=${data.game_id}`)}>
        进入观战页查看详情 →
      </button>
    </div>
  )
}

// ── Main component ─────────────────────────────────
export default function LobbyPage() {
  const navigate = useNavigate()
  const [pollInterval, setPollInterval] = useState(3000)
  const { data, error, isLoading } = usePolling('/v1/lobby/status', { intervalMs: pollInterval })
  const [localSlots, setLocalSlots] = useState(null)
  const [msg, setMsg] = useState(null)
  const msgTimer = useRef(null)
  const pendingRef = useRef(null)

  useEffect(() => {
    if (!data?.status) return
    const next = data.status === 'finished' ? null
      : data.status === 'countdown' ? 1000
      : data.status === 'lobby' ? 5000
      : 3000
    setPollInterval(prev => prev === next ? prev : next)
  }, [data?.status])

  const slots = localSlots || data?.slots
  const gameStatus = data?.status
  const gameId = data?.game_id
  const winner = data?.winner
  const tick = data?.tick
  const maxTicks = data?.max_ticks
  const countdownDeadline = data?.countdown_deadline

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

  function _revertSlot(faction) {
    setLocalSlots(prev => {
      if (!prev) return prev
      const next = { ...prev }
      delete next[faction]
      return next
    })
  }

  async function actJoin(faction) {
    flash(null)
    pendingRef.current = { faction, check: s => s.status === 'occupied', until: Date.now() + 5000 }
    setLocalSlots(prev => ({ ...(prev || slots), [faction]: { status: 'occupied', ready: false, agent_display_name: '你', ip: '***' } }))
    try {
      await api.joinLobby(faction)
      flash(`已加入 ${faction}`)
    } catch (e) {
      _revertSlot(faction); pendingRef.current = null
      if (e.code === 'COUNTDOWN_STARTED') flash('倒计时已启动，无法加入')
      else flash(`加入失败: ${e.message}`)
    }
  }

  async function actAssignAI(faction) {
    flash(null)
    pendingRef.current = { faction, check: s => s.status === 'ai_managed', until: Date.now() + 5000 }
    setLocalSlots(prev => ({ ...(prev || slots), [faction]: { status: 'ai_managed', ready: true, agent_display_name: `托管AI-${faction}` } }))
    try { await api.assignAI(faction); flash(`已配 ${faction} 为 AI 托管`) }
    catch (e) { _revertSlot(faction); pendingRef.current = null; flash(`配 AI 失败: ${e.message}`) }
  }

  async function actReleaseAI(faction) {
    flash(null)
    pendingRef.current = { faction, check: s => s.status === 'open', until: Date.now() + 5000 }
    setLocalSlots(prev => ({ ...(prev || slots), [faction]: { status: 'open', ready: false } }))
    try { await api.releaseAI(faction); flash(`已释放 ${faction} AI 托管`) }
    catch (e) { _revertSlot(faction); pendingRef.current = null; flash(`释放失败: ${e.message}`) }
  }

  async function actReady(faction, token) {
    flash(null)
    pendingRef.current = { faction, check: s => s.ready === true, until: Date.now() + 5000 }
    setLocalSlots(prev => ({ ...(prev || slots), [faction]: { ...((prev || slots)[faction]), ready: true } }))
    try { await api.ready(token); flash('已就绪') }
    catch (e) { _revertSlot(faction); pendingRef.current = null; flash(`Ready 失败: ${e.message}`) }
  }

  if (isLoading && !data) return <div className="lb-loading">加载中…</div>

  return (
    <div className="lb-page">
      {/* ── Error / Msg ────────────────────────── */}
      {error && <div className="lb-error">Failed to fetch: {error}</div>}
      {msg && <div className="lb-msg">{msg}</div>}

      {/* ── Header ─────────────────────────────── */}
      <div className="lb-header">
        <div className="lb-title-row">
          <h1 className="lb-title">对战大厅</h1>
          <span className={`lb-status lb-st-${gameStatus}`}>{gameStatus}</span>
        </div>
        <div className="lb-meta">
          Game <span className="lb-mono">{gameId ?? '?'}</span>
          {' · '}Tick {tick ?? '?'}/{maxTicks ?? '?'}
          {data?.spectator_count > 0 && <> · {data.spectator_count} 观战中</>}
        </div>
      </div>

      {/* ── Finished banner ────────────────────── */}
      {gameStatus === 'finished' && winner && (
        <div className="lb-finished">
          胜方: <span style={{ color: FACTION_COLORS[winner], fontWeight: 700 }}>
            {winner} · {FACTION_MONARCHS[winner]}
          </span>
          {' · '}
          <span className="lb-link" onClick={() => navigate(`/spectate?game=${gameId}`)}>
            查看战报与评书 →
          </span>
        </div>
      )}

      {/* ── Countdown ──────────────────────────── */}
      {gameStatus === 'countdown' && countdownDeadline && (
        <CountdownOverlay deadline={countdownDeadline} />
      )}

      {/* ── Slot cards ─────────────────────────── */}
      <div className="lb-slots">
        {FACTIONS.map(f => {
          const slot = slots?.[f]
          const ui = slotUI(slot, f, gameStatus)
          return (
            <div key={f} className={`lb-slot lb-s-${ui.cssClass}`} style={{ borderColor: FACTION_COLORS[f] }}>
              <div className="lb-s-faction" style={{ color: FACTION_COLORS[f] }}>
                {f}<span className="lb-s-monarch"> · {FACTION_MONARCHS[f]}</span>
              </div>
              <div className="lb-s-label">{ui.label}</div>
              <div className="lb-s-desc">{ui.description}</div>

              {ui.canAct && (
                <div className="lb-s-btns">
                  {ui.actions?.includes('assign_ai') && (
                    <button className="lb-btn lb-btn-ai" onClick={() => actAssignAI(f)}>配 AI 托管</button>
                  )}
                  {ui.actions?.includes('join') && (
                    <button className="lb-btn lb-btn-join" onClick={() => actJoin(f)}>加入 {f}</button>
                  )}
                  {ui.actions?.includes('grab') && (
                    <button className="lb-btn lb-btn-grab" onClick={() => actJoin(f)}>抢占 {f}</button>
                  )}
                  {ui.actions?.includes('release_ai') && (
                    <button className="lb-btn lb-btn-release" onClick={() => actReleaseAI(f)}>释放 AI</button>
                  )}
                  {ui.actions?.includes('ready') && (
                    <span className="lb-s-need-ready">等待 Ready</span>
                  )}
                </div>
              )}

              {slot?.status === 'disconnected' && slot?.reconnect_remaining_sec > 0 && (
                <div className="lb-s-reconnect">
                  该位置玩家掉线，{fmtDuration(slot.reconnect_remaining_sec)} 后自动释放给托管 AI（也可立即点击抢占）
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* ── Battle preview ──────────────────────── */}
      <BattlePreview data={data} />

      {/* ── Spectate-only ───────────────────────── */}
      <div className="lb-footer">
        <button className="btn-ghost" onClick={() => navigate(`/spectate?game=${gameId}`)}>
          仅观战（不占槽位）
        </button>
      </div>
    </div>
  )
}
