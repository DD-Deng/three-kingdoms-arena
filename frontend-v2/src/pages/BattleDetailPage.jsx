import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { FACTION_COLORS, FACTIONS } from '../constants'

export default function BattleDetailPage() {
  const { id } = useParams()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    fetch(`/v1/games/${id}/result`)
      .then(async r => {
        if (!r.ok) throw new Error(r.status === 425 ? '对局仍在进行中' : `HTTP ${r.status}`)
        const json = await r.json()
        if (!cancelled) { setData(json); setLoading(false) }
      })
      .catch(e => { if (!cancelled) { setError(e.message); setLoading(false) } })
    return () => { cancelled = true }
  }, [id])

  if (loading) return <div className="bt-loading">加载中…</div>
  if (error) return <div className="bt-error">加载失败: {error}</div>
  if (!data) return null

  const winner = data.winner
  const cities = data.final_cities || []
  const stats = data.faction_stats || {}
  const events = data.key_events || []

  return (
    <div className="bt-page">
      <Link to="/battles" className="bt-back">← 返回战报列表</Link>

      {/* ── Header ──────────────────────────────── */}
      <div className="bd-header">
        <h1>Game #{data.game_id}</h1>
        <div className="bd-meta">
          {winner && <span className="bd-winner" style={{ color: FACTION_COLORS[winner] }}>胜方: {winner}</span>}
          <span>{data.tick_finished} ticks</span>
          {data.duration_sec != null && <span>{Math.floor(data.duration_sec / 60)} 分钟</span>}
          <span>{data.winner_reason === 'elimination' ? '灭国胜利' : '城数判定'}</span>
        </div>
      </div>

      {/* ── Final cities ─────────────────────────── */}
      <div className="bd-section">
        <h2>终局城池</h2>
        <div className="bd-cities">
          {cities.map(c => (
            <div key={c.name} className="bd-city" style={{ borderLeft: `3px solid ${FACTION_COLORS[c.owner] || 'var(--ink-mute)'}` }}>
              <span className="bd-city-name">{c.name}</span>
              <span className="bd-city-owner" style={{ color: FACTION_COLORS[c.owner] || 'var(--ink-mute)' }}>
                {c.owner || '中立'}
              </span>
              <span className="bd-city-troops">{c.troops} 兵</span>
            </div>
          ))}
        </div>
      </div>

      {/* ── Faction stats ────────────────────────── */}
      <div className="bd-section">
        <h2>阵营统计</h2>
        <div className="bd-stats-grid">
          {FACTIONS.map(f => {
            const s = stats[f]
            if (!s) return null
            return (
              <div key={f} className="bd-stat-card" style={{ borderLeft: `3px solid ${FACTION_COLORS[f]}` }}>
                <div className="bd-stat-faction" style={{ color: FACTION_COLORS[f] }}>{f}</div>
                <div className="bd-stat-row"><span>终局城池</span><span>{s.final_cities}</span></div>
                <div className="bd-stat-row"><span>峰值城池</span><span>{s.peak_cities}</span></div>
                <div className="bd-stat-row"><span>击杀</span><span>{s.kills}</span></div>
                <div className="bd-stat-row"><span>损失</span><span>{s.losses}</span></div>
              </div>
            )
          })}
        </div>
      </div>

      {/* ── Key events timeline ──────────────────── */}
      {events.length > 0 && (
        <div className="bd-section">
          <h2>关键事件</h2>
          <div className="bd-timeline">
            {events.map((evt, i) => (
              <div key={i} className="bd-tl-item">
                <span className="bd-tl-tick">T{evt.tick}</span>
                <span className="bd-tl-desc">{evt.event}</span>
                {evt.significance === 'high' && <span className="bd-tl-high">关键</span>}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Commentary link ──────────────────────── */}
      <div className="bd-commentary-link">
        <Link to={`/battles/${id}/commentary`} className="btn-primary">
          📖 查看完整评书
        </Link>
      </div>
    </div>
  )
}
