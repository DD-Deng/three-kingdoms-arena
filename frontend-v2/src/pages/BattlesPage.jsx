import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { FACTION_COLORS } from '../constants'

export default function BattlesPage() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    fetch('/api/public/battles?page_size=50')
      .then(async r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        const json = await r.json()
        if (!cancelled) { setData(json); setLoading(false) }
      })
      .catch(e => { if (!cancelled) { setError(e.message); setLoading(false) } })
    return () => { cancelled = true }
  }, [])

  if (loading) return <div className="bt-loading">加载中…</div>
  if (error) return <div className="bt-error">加载失败: {error}</div>

  const battles = (data?.battles || []).filter(b => b.total_ticks > 0 || b.winner)

  return (
    <div className="bt-page">
      <div className="bt-header">
        <div className="md-eyebrow">BATTLE HISTORY</div>
        <h1 className="md-title">历史战报</h1>
      </div>

      {battles.length === 0 ? (
        <div className="bt-empty">
          <p>暂无已完结的对局</p>
          <p className="bt-empty-hint">启动一局游戏并让它完整跑到结束，战报就会出现在这里。</p>
        </div>
      ) : (
        <div className="bt-list">
          {battles.map(b => (
            <Link to={`/battles/${b.game_id}`} key={b.battle_id} className="bt-row">
              <span className="bt-id">#{b.game_id}</span>
              <span className="bt-mid">
                <span className="bt-line1">
                  <span className="bt-model">{b.model}</span>
                  {b.winner && (
                    <span className="bt-winner" style={{ color: FACTION_COLORS[b.winner] || 'var(--ink)' }}>
                      {b.winner} 胜
                    </span>
                  )}
                </span>
                <span className="bt-line2">
                  <span>{b.total_ticks} ticks</span>
                  {b.has_commentary && <span className="bt-has-commentary">📖 有评书</span>}
                </span>
              </span>
              <span className="bt-ago">{b.created_at ? new Date(b.created_at).toLocaleDateString('zh-CN') : ''}</span>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
