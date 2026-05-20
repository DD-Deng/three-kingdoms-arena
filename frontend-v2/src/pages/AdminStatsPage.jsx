import { useState, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { getAdminToken, clearAdminToken } from './AdminLoginPage'
import { FACTION_COLORS, FACTIONS } from '../constants'

export default function AdminStatsPage() {
  const navigate = useNavigate()
  const token = getAdminToken()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!token) { navigate('/admin/login'); return }
    let cancelled = false
    fetch(`/api/admin/stats?token=${encodeURIComponent(token)}`)
      .then(async r => {
        if (r.status === 401) { clearAdminToken(); navigate('/admin/login'); return }
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        const json = await r.json()
        if (!cancelled) { setData(json); setLoading(false) }
      })
      .catch(e => { if (!cancelled) { setError(e.message); setLoading(false) } })
    return () => { cancelled = true }
  }, [token, navigate])

  if (!token) return null
  if (loading) return <div className="adm-loading">加载中…</div>
  if (error) return <div className="adm-error">{error}</div>
  if (!data) return null

  const modelStats = data.model_stats || {}
  const factionWins = data.faction_wins || {}

  return (
    <div className="adm-page">
      <div className="adm-topbar">
        <h1>管理后台</h1>
        <div className="adm-topbar-right">
          <Link to="/admin" className="adm-link">← 返回列表</Link>
          <button className="btn-ghost" onClick={() => { clearAdminToken(); navigate('/admin/login') }}>退出</button>
        </div>
      </div>

      {/* Overview */}
      <div className="adm-stats-overview">
        <div className="adm-stat-big">{data.total_battles}<span>总对局</span></div>
        <div className="adm-stat-big">{data.avg_ticks}<span>平均回合</span></div>
      </div>

      {/* Faction wins */}
      <div className="adm-section">
        <h2>阵营胜率</h2>
        <div className="adm-faction-wins">
          {FACTIONS.map(f => (
            <div key={f} className="adm-fw-item" style={{ borderLeft: `3px solid ${FACTION_COLORS[f]}` }}>
              <span className="adm-fw-faction" style={{ color: FACTION_COLORS[f] }}>{f}</span>
              <span className="adm-fw-count">{factionWins[f] || 0} 胜</span>
            </div>
          ))}
        </div>
      </div>

      {/* Model stats */}
      <div className="adm-section">
        <h2>模型统计</h2>
        <table className="adm-table">
          <thead>
            <tr><th>模型</th><th>总局数</th><th>胜场</th><th>胜率</th><th>超时</th><th>错误</th></tr>
          </thead>
          <tbody>
            {Object.entries(modelStats).length === 0 ? (
              <tr><td colSpan={6} className="adm-empty">暂无数据</td></tr>
            ) : Object.entries(modelStats).map(([m, s]) => (
              <tr key={m}>
                <td>{m}</td>
                <td>{s.total}</td>
                <td>{s.wins}</td>
                <td>{s.total > 0 ? Math.round(s.wins / s.total * 100) : 0}%</td>
                <td>{s.max_ticks}</td>
                <td>{s.errors}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
