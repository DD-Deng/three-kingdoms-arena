import { useSearchParams } from 'react-router-dom'
import usePolling from './hooks/usePolling'

const ALL_CITIES = ['洛阳', '长安', '邺城', '宛城', '襄阳', '成都', '建业']
const FACTIONS = ['蜀', '魏', '吴']
const FACTION_COLORS = {
  蜀: 'var(--shu)',
  魏: 'var(--wei)',
  吴: 'var(--wu)',
}

function ownerColor(owner) {
  return FACTION_COLORS[owner] || 'var(--ink-dim)'
}

export default function SpectateV2() {
  const [params] = useSearchParams()
  const gameId = params.get('game')

  // Use current-game endpoint; if gameId is specified, could use /games/{id}/state
  const url = gameId
    ? `/current-game`  // public fallback — /games/{id}/state needs auth
    : '/current-game'

  const { data, error, loading } = usePolling(url, 3000)

  if (loading && !data) {
    return <div className="page"><p>加载中…</p></div>
  }

  if (error) {
    console.error('SpectateV2 fetch error:', error)
  }

  console.log('SpectateV2 poll:', {
    game_id: data?.game_id,
    status: data?.status,
    tick: data?.tick,
    cities: data?.cities?.map(c => `${c.name}:${c.owner ?? '中立'}:${c.troops}`),
    factions: data?.factions,
    events_count: data?.events?.length,
  })

  const gid = data?.game_id ?? '?'
  const tick = data?.tick ?? '?'
  const maxTicks = data?.max_ticks ?? '?'
  const status = data?.status ?? '?'

  const cityMap = {}
  if (data?.cities) {
    for (const c of data.cities) {
      cityMap[c.name] = c
    }
  }

  return (
    <div className="page">
      {error && (
        <div className="error-banner">
          Failed to fetch: {error}
        </div>
      )}

      <h1>
        Game <span className="game-id">#{gid}</span>
        {' · '}Tick <span className="tick-num">{tick}</span>/{maxTicks}
        {' · '}status: <span className="status-tag">{status}</span>
      </h1>

      <h3>7 城兵力</h3>
      <table className="city-table">
        <thead>
          <tr>
            <th>城</th>
            <th>归属</th>
            <th>兵力</th>
          </tr>
        </thead>
        <tbody>
          {ALL_CITIES.map((name) => {
            const c = cityMap[name]
            return (
              <tr key={name}>
                <td>{name}</td>
                <td style={{ color: ownerColor(c?.owner) }}>
                  {c?.owner || '中立'}
                </td>
                <td className="troop-num">{c?.troops ?? '—'}</td>
              </tr>
            )
          })}
        </tbody>
      </table>

      <h3>三阵营总览</h3>
      <table className="faction-table">
        <thead>
          <tr>
            <th>阵营</th>
            <th>城数</th>
            <th>总兵力</th>
            <th>总粮草</th>
          </tr>
        </thead>
        <tbody>
          {FACTIONS.map((f) => {
            const fs = data?.factions?.[f]
            return (
              <tr key={f}>
                <td style={{ color: FACTION_COLORS[f], fontWeight: 600 }}>{f}</td>
                <td>{fs?.cities ?? '—'}</td>
                <td>{fs?.troops ?? '—'}</td>
                <td className="ink-dim">{fs?.grain ?? '—'}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
