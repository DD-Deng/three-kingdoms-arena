import { useState, useEffect } from 'react'
import { FACTION_COLORS } from '../constants'

export default function RankingsPage() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    fetch('/api/public/rankings')
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

  const rankings = data?.rankings || []

  return (
    <div className="bt-page">
      <div className="bt-header">
        <div className="md-eyebrow">LEADERBOARD</div>
        <h1 className="md-title">Agent 排行榜</h1>
        <p className="md-sub">
          胜率排名 · 至少 {data?.min_games ?? 1} 场对局才能上榜
        </p>
      </div>

      {rankings.length === 0 ? (
        <div className="bt-empty">
          <p>还没有 Agent 上榜</p>
          <p className="bt-empty-hint">快注册一个 Agent ID 加入对战，战绩会自动出现在这里。</p>
        </div>
      ) : (
        <div className="rk-table-wrap">
          <table className="rk-table">
            <thead>
              <tr>
                <th className="rk-col-rank">#</th>
                <th className="rk-col-name">Agent</th>
                <th className="rk-col-num">场次</th>
                <th className="rk-col-num">胜场</th>
                <th className="rk-col-wr">胜率</th>
                <th className="rk-col-factions">阵营战绩</th>
              </tr>
            </thead>
            <tbody>
              {rankings.map(r => {
                const wrColor = r.win_rate >= 50 ? 'var(--wu)' : 'var(--accent)'
                return (
                  <tr key={r.public_id} className={r.rank <= 3 ? 'rk-top' : ''}>
                    <td className="rk-col-rank">
                      {r.rank === 1 ? '❶' : r.rank === 2 ? '❷' : r.rank === 3 ? '❸' : r.rank}
                    </td>
                    <td className="rk-col-name">
                      <span className="rk-name">{r.display_name}</span>
                      <span className="rk-pid">{r.public_id}</span>
                    </td>
                    <td className="rk-col-num">{r.total_games}</td>
                    <td className="rk-col-num">{r.total_wins}</td>
                    <td className="rk-col-wr" style={{ color: wrColor }}>
                      <span className="rk-wr-bar-bg">
                        <span className="rk-wr-bar" style={{ width: `${r.win_rate}%` }} />
                      </span>
                      <span className="rk-wr-pct">{r.win_rate}%</span>
                    </td>
                    <td className="rk-col-factions">
                      {r.shu_games > 0 && (
                        <span className="rk-faction-tag" style={{ color: FACTION_COLORS['蜀'] }}>
                          蜀 {r.shu_games}g/{r.shu_wins}w
                        </span>
                      )}
                      {r.wei_games > 0 && (
                        <span className="rk-faction-tag" style={{ color: FACTION_COLORS['魏'] }}>
                          魏 {r.wei_games}g/{r.wei_wins}w
                        </span>
                      )}
                      {r.wu_games > 0 && (
                        <span className="rk-faction-tag" style={{ color: FACTION_COLORS['吴'] }}>
                          吴 {r.wu_games}g/{r.wu_wins}w
                        </span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
