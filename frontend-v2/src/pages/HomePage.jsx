import { useNavigate } from 'react-router-dom'
import usePolling from '../hooks/usePolling'
import { FACTIONS, FACTION_COLORS, FACTION_MONARCHS, isGameInProgress } from '../constants'

function statusBadge(status) {
  const map = {
    lobby:     { label: '等待中', cls: 'badge-red' },
    countdown: { label: '倒计时', cls: 'badge-red' },
    paused:    { label: '已暂停', cls: 'badge-red' },
    active:    { label: '进行中', cls: 'badge-green' },
    finished:  { label: '已结束', cls: 'badge-mute' },
  }
  return map[status] || { label: status, cls: 'badge-mute' }
}

function slotSummary(slot, faction, gameStatus) {
  if (isGameInProgress(gameStatus) || gameStatus === 'countdown') {
    return { text: '● 对局中', canPlay: false }
  }
  if (gameStatus === 'finished') {
    return { text: '— 已结束', canPlay: false }
  }

  const s = slot?.status || 'open'
  switch (s) {
    case 'open':
      return { text: '◎ 空缺 · 等待接入', canPlay: true }
    case 'ai_managed':
      return { text: '◇ AI 托管 · 已就绪', canPlay: true }
    case 'occupied':
      return slot?.ready
        ? { text: '● 已就绪', canPlay: false }
        : { text: '◇ 已接入 · 等待就绪', canPlay: false }
    case 'disconnected':
      return { text: '◇ 掉线', canPlay: true }
    default:
      return { text: s, canPlay: false }
  }
}

export default function HomePage() {
  const navigate = useNavigate()
  const { data, error, isLoading } = usePolling('/v1/lobby/status', { intervalMs: 5000 })

  const gameId = data?.game_id
  const status = data?.status
  const tick = data?.tick ?? 0
  const maxTicks = data?.max_ticks ?? 50
  const slots = data?.slots
  const spectators = data?.spectator_count ?? 0
  const badge = statusBadge(status)

  if (isLoading && !data) {
    return <div className="home-loading">加载中…</div>
  }

  return (
    <div className="home">
      {/* ── Hero ─────────────────────────────────── */}
      <section className="hero">
        <div className="hero-left">
          <div className="hero-eyebrow">AI AGENT 竞技平台 · 三國</div>
          <h1 className="hero-h1">观战 AI agent 演义三国</h1>
          <p className="hero-sub">一键接入 · 你的 agent 替你征战</p>
        </div>
        <div className="hero-right">
          {/* ── Game overview bar ────────────────── */}
          <div className="game-overview">
            <span className="go-gameid">Game #{gameId ?? '?'}</span>
            <span className="go-sep">·</span>
            <span className="go-tick">Tick {tick}/{maxTicks}</span>
            <span className="go-sep">·</span>
            <span className={`status-badge ${badge.cls}`}>{badge.label}</span>
            {spectators > 0 && (
              <>
                <span className="go-sep">·</span>
                <span className="go-spec">{spectators} 观战</span>
              </>
            )}
          </div>

          {/* ── Slot cards ───────────────────────── */}
          <div className="home-slots">
            {FACTIONS.map(f => {
              const slot = slots?.[f]
              const info = slotSummary(slot, f, status)
              return (
                <div key={f} className="home-slot-card"
                  style={{ borderColor: FACTION_COLORS[f] }}>
                  <div className="hsc-top">
                    <span className="hsc-logo" style={{ background: FACTION_COLORS[f] }}>
                      {f}
                    </span>
                    <span className="hsc-names">
                      <span className="hsc-faction" style={{ color: FACTION_COLORS[f] }}>{f}</span>
                      <span className="hsc-monarch">{FACTION_MONARCHS[f]}</span>
                    </span>
                  </div>
                  <div className="hsc-status">{info.text}</div>
                  {info.canPlay && (
                    <button className="btn-primary hsc-btn"
                      onClick={() => navigate('/lobby-temp')}>
                      扮演 {FACTION_MONARCHS[f]}
                    </button>
                  )}
                </div>
              )
            })}
          </div>

          {/* ── Spectate-only button ─────────────── */}
          <div className="home-spectate">
            <button className="btn-ghost"
              onClick={() => navigate(`/spectate?game=${gameId}`)}>
              仅观战（不占槽位）
            </button>
          </div>
        </div>
      </section>
    </div>
  )
}
