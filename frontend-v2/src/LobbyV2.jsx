import { useState } from 'react'
import usePolling from './hooks/usePolling'

const FACTIONS = ['蜀', '魏', '吴']
const FACTION_COLORS = {
  蜀: 'var(--shu)',
  魏: 'var(--wei)',
  吴: 'var(--wu)',
}

function slotLabel(slot) {
  if (!slot) return '—'
  if (slot.status === 'open') return '空缺'
  if (slot.status === 'disconnected') return '掉线'
  if (slot.status === 'ai_managed') return 'AI 托管'
  if (slot.ready) return '已就绪'
  return '已占用'
}

export default function LobbyV2() {
  const { data, error, loading } = usePolling('/v1/lobby/status', 3000)
  const [joinMsg, setJoinMsg] = useState(null)

  if (loading && !data) {
    return <div className="page"><p>加载中…</p></div>
  }

  if (error) {
    console.error('LobbyV2 fetch error:', error)
  }

  console.log('LobbyV2 poll:', {
    game_id: data?.game_id,
    status: data?.status,
    tick: data?.tick,
    slot_states: data?.slots,
  })

  const gameId = data?.game_id ?? '?'
  const status = data?.status ?? '?'

  async function handleJoin(faction) {
    setJoinMsg(null)
    try {
      const res = await fetch('/v1/lobby/join', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ faction }),
      })
      const body = await res.json()
      if (!res.ok) throw new Error(body.detail || `HTTP ${res.status}`)
      setJoinMsg(`Joined ${faction} — token: ${body.session_token?.slice(0, 12)}…`)
    } catch (e) {
      setJoinMsg(`Join failed: ${e.message}`)
    }
  }

  async function handleReady(token) {
    try {
      const res = await fetch('/v1/lobby/ready', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token }),
      })
      if (!res.ok) {
        const body = await res.json()
        throw new Error(body.detail || `HTTP ${res.status}`)
      }
      setJoinMsg('Ready OK')
    } catch (e) {
      setJoinMsg(`Ready failed: ${e.message}`)
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
        Lobby Status: <span className="status-tag">{status}</span>
        {' · '}Game <span className="game-id">#{gameId}</span>
        {data?.tick != null && <> · Tick {data.tick}/{data.max_ticks}</>}
      </h1>

      {joinMsg && <div className="msg-banner">{joinMsg}</div>}

      <div className="slot-row">
        {FACTIONS.map((f) => {
          const slot = data?.slots?.[f]
          return (
            <div key={f} className="slot-card" style={{ borderColor: FACTION_COLORS[f] }}>
              <div className="slot-faction" style={{ color: FACTION_COLORS[f] }}>
                {f}
              </div>
              <div className="slot-detail">
                <span className="slot-label">{slotLabel(slot)}</span>
                {slot?.ip && <span className="slot-ip">IP: {slot.ip}</span>}
                {slot?.disconnected_sec != null && (
                  <span className="slot-dc">掉线 {slot.disconnected_sec}s</span>
                )}
              </div>
              <div className="slot-actions">
                {slot?.status === 'open' && (
                  <button onClick={() => handleJoin(f)}>加入 {f}</button>
                )}
                {slot?.ready === false && slot?.status !== 'open' && (
                  <span className="slot-not-ready">未就绪</span>
                )}
                {slot?.ready === true && (
                  <span className="slot-ready">✓ 已就绪</span>
                )}
              </div>
            </div>
          )
        })}
      </div>

      <div className="debug-section">
        <h4>Debug: quick ready (蜀 slot)</h4>
        <button
          onClick={async () => {
            // re-join to get a fresh token
            try {
              const j = await fetch('/v1/lobby/join', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ faction: '蜀' }),
              })
              const b = await j.json()
              if (!j.ok) throw new Error(b.detail)
              handleReady(b.session_token)
            } catch (e) {
              setJoinMsg(`Quick ready failed: ${e.message}`)
            }
          }}
        >
          Join 蜀 + Ready
        </button>
      </div>
    </div>
  )
}
