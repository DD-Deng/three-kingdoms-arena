import { useState, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { getAdminToken, clearAdminToken } from './AdminLoginPage'
import { FACTION_COLORS } from '../constants'

export default function AdminPage() {
  const navigate = useNavigate()
  const token = getAdminToken()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!token) { navigate('/admin/login'); return }
    let cancelled = false
    fetch(`/api/admin/battles?token=${encodeURIComponent(token)}`)
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

  const battles = data?.battles || []

  return (
    <div className="adm-page">
      <div className="adm-topbar">
        <h1>管理后台</h1>
        <div className="adm-topbar-right">
          <Link to="/admin/stats" className="adm-link">统计面板</Link>
          <button className="btn-ghost" onClick={() => { clearAdminToken(); navigate('/admin/login') }}>退出</button>
        </div>
      </div>

      {error && <div className="adm-error">{error}</div>}

      <div className="adm-section">
        <h2>对战列表</h2>
        <table className="adm-table">
          <thead>
            <tr>
              <th>ID</th><th>Game #</th><th>模型</th><th>胜方</th><th>Ticks</th><th>状态</th><th>时间</th>
            </tr>
          </thead>
          <tbody>
            {battles.length === 0 ? (
              <tr><td colSpan={7} className="adm-empty">暂无数据</td></tr>
            ) : battles.map(b => (
              <tr key={b.battle_id}>
                <td className="adm-mono">
                  <Link to={`/admin/battles/${b.battle_id}`}>#{b.battle_id}</Link>
                </td>
                <td className="adm-mono">{b.game_id}</td>
                <td>{b.model}</td>
                <td style={{ color: FACTION_COLORS[b.winner] || 'inherit' }}>{b.winner || '—'}</td>
                <td>{b.total_ticks}</td>
                <td>{b.status}</td>
                <td className="adm-mono">{b.created_at ? new Date(b.created_at).toLocaleDateString('zh-CN') : ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
