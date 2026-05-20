import { useState, useEffect } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { getAdminToken, clearAdminToken } from './AdminLoginPage'
import { FACTION_COLORS, FACTIONS } from '../constants'

export default function AdminBattleDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const token = getAdminToken()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!token) { navigate('/admin/login'); return }
    let cancelled = false
    fetch(`/api/admin/battles/${id}?token=${encodeURIComponent(token)}`)
      .then(async r => {
        if (r.status === 401) { clearAdminToken(); navigate('/admin/login'); return }
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        const json = await r.json()
        if (!cancelled) { setData(json); setLoading(false) }
      })
      .catch(e => { if (!cancelled) { setError(e.message); setLoading(false) } })
    return () => { cancelled = true }
  }, [id, token, navigate])

  if (!token) return null
  if (loading) return <div className="adm-loading">加载中…</div>
  if (error) return <div className="adm-error">{error}</div>
  if (!data) return null

  const ticks = data.ticks || []
  const powerCurve = data.power_curve || []
  const winner = data.battle?.winner
  const summary = data.battle?.summary

  return (
    <div className="adm-page">
      <Link to="/admin" className="bt-back">← 返回列表</Link>

      <div className="bd-header">
        <h1>Battle #{data.battle?.battle_id}</h1>
        <div className="bd-meta">
          <span>Game #{data.battle?.game_id}</span>
          <span>{data.battle?.model}</span>
          {winner && <span style={{ color: FACTION_COLORS[winner] }}>胜方: {winner}</span>}
          <span>{data.battle?.total_ticks} ticks</span>
          <span>{data.battle?.status}</span>
        </div>
      </div>

      {/* Faction summary */}
      {summary && (
        <div className="bd-section">
          <h2>阵营终局数据</h2>
          <div className="bd-stats-grid">
            {FACTIONS.map(f => {
              const s = summary[f]
              if (!s) return null
              return (
                <div key={f} className="bd-stat-card" style={{ borderLeft: `3px solid ${FACTION_COLORS[f]}` }}>
                  <div className="bd-stat-faction" style={{ color: FACTION_COLORS[f] }}>{f}</div>
                  {Object.entries(s).map(([k, v]) => (
                    <div key={k} className="bd-stat-row"><span>{k}</span><span>{typeof v === 'number' ? v.toLocaleString() : String(v)}</span></div>
                  ))}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Ticks table */}
      {ticks.length > 0 && (
        <div className="bd-section">
          <h2>Tick 数据 ({ticks.length} ticks)</h2>
          <table className="adm-table">
            <thead>
              <tr>
                <th>Tick</th><th>事件数</th><th>外交数</th><th>城池归属</th>
              </tr>
            </thead>
            <tbody>
              {ticks.map(t => {
                const citySummary = (t.cities || []).map(c => `${c.name}:${c.owner || '中'}`).join(' ')
                return (
                  <tr key={t.tick}>
                    <td className="adm-mono">{t.tick}</td>
                    <td>{(t.events || []).length}</td>
                    <td>{(t.diplomacy || []).length}</td>
                    <td style={{ fontSize: 11 }}>{citySummary || '—'}</td>
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
