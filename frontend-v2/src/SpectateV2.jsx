import { useState, useRef, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import usePolling from './hooks/usePolling'
import { api } from './api'
import { FACTIONS, FACTION_COLORS, FACTION_MONARCHS, CITY_POSITIONS, ADJACENCY } from './constants'

// ── Compute faction summary from cities ─────────
function computeFactions(cities) {
  const factions = { 蜀: { cities: 0, troops: 0 }, 魏: { cities: 0, troops: 0 }, 吴: { cities: 0, troops: 0 } }
  if (!cities) return factions
  for (const c of cities) {
    if (c.owner && factions[c.owner]) {
      factions[c.owner].cities += 1
      factions[c.owner].troops += c.troops || 0
    }
  }
  return factions
}

function computeEvalPower(cities) {
  const factions = computeFactions(cities)
  const power = {}
  for (const f of FACTIONS) {
    power[f] = factions[f].cities * 3 + factions[f].troops * 0.001
  }
  const total = power.蜀 + power.魏 + power.吴 || 1
  for (const f of FACTIONS) {
    power[f] = Math.round((power[f] / total) * 100)
  }
  return power
}

// ── City map SVG ────────────────────────────────
function CityMap({ cities, events, prevCitiesRef }) {
  const [flashes, setFlashes] = useState({})
  const [arrows, setArrows] = useState([])

  // Detect captures → flash + arrow
  useEffect(() => {
    if (!events || !events.length) return
    const latest = events[events.length - 1]
    if (latest?.type === 'attack' && latest?.city) {
      const city = latest.city
      setFlashes(prev => ({ ...prev, [city]: true }))
      setTimeout(() => setFlashes(prev => ({ ...prev, [city]: false })), 1200)
    }
  }, [events])

  const cityMap = {}
  if (cities) for (const c of cities) cityMap[c.name] = c

  return (
    <svg viewBox="0 0 300 260" className="city-map-svg">
      {/* Adjacency lines */}
      {ADJACENCY.map(([a, b]) => {
        const pa = CITY_POSITIONS[a], pb = CITY_POSITIONS[b]
        return (
          <line key={`${a}-${b}`} x1={pa.x} y1={pa.y} x2={pb.x} y2={pb.y}
            className="map-adjacency" />
        )
      })}

      {/* Cities */}
      {Object.entries(CITY_POSITIONS).map(([name, pos]) => {
        const c = cityMap[name]
        const owner = c?.owner
        const troops = c?.troops ?? '?'
        const color = FACTION_COLORS[owner] || '#555'
        const flash = flashes[name]

        return (
          <g key={name} className={`map-city ${flash ? 'map-city-flash' : ''}`}>
            <rect x={pos.x - 28} y={pos.y - 14} width={56} height={28}
              rx={6} fill="var(--panel)" stroke={color} strokeWidth={1.5} />
            <text x={pos.x} y={pos.y - 1} textAnchor="middle"
              fill={color} fontSize={11} fontWeight={600}>{name}</text>
            <text x={pos.x} y={pos.y + 12} textAnchor="middle"
              fill={color} fontSize={10} fontFamily="var(--font-mono)">
              {owner || '—'} {troops}
            </text>
          </g>
        )
      })}

      {/* Attack arrows */}
      {arrows.map((a, i) => {
        const from = CITY_POSITIONS[a.from], to = CITY_POSITIONS[a.to]
        if (!from || !to) return null
        return (
          <line key={i} x1={from.x} y1={from.y} x2={to.x} y2={to.y}
            className="map-arrow" stroke={FACTION_COLORS[a.faction] || '#888'}
            strokeWidth={2} markerEnd="url(#arrowhead)" />
        )
      })}
      <defs>
        <marker id="arrowhead" markerWidth={8} markerHeight={6} refX={8} refY={3} orient="auto">
          <polygon points="0 0, 8 3, 0 6" fill="#888" />
        </marker>
      </defs>
    </svg>
  )
}

// ── Eval bar ────────────────────────────────────
function EvalBar({ cities }) {
  const power = computeEvalPower(cities)
  return (
    <div className="eval-bar-wrap">
      <div className="eval-bar">
        {FACTIONS.map(f => (
          <div key={f} className="eval-segment"
            style={{
              width: `${power[f]}%`,
              background: FACTION_COLORS[f],
            }}
            title={`${f}: ${power[f]}%`}
          />
        ))}
      </div>
      <div className="eval-labels">
        {FACTIONS.map(f => (
          <span key={f} style={{ color: FACTION_COLORS[f] }}>
            {f} {power[f]}%
          </span>
        ))}
      </div>
    </div>
  )
}

// ── Faction info cards ──────────────────────────
function FactionCards({ cities, agents }) {
  const factions = computeFactions(cities)
  const agentMap = {}
  if (agents) for (const a of agents) agentMap[a.faction] = a

  return (
    <div className="faction-cards-row">
      {FACTIONS.map(f => {
        const fs = factions[f]
        const agent = agentMap[f]
        return (
          <div key={f} className="faction-card"
            style={{ borderLeft: `3px solid ${FACTION_COLORS[f]}` }}>
            <div className="fc-header">
              <span className="fc-faction" style={{ color: FACTION_COLORS[f] }}>{f}</span>
              <span className="fc-monarch">{FACTION_MONARCHS[f]}</span>
            </div>
            <div className="fc-stats">
              <div className="fc-stat">
                <span className="fc-label">城</span>
                <span className="fc-value">{fs.cities}</span>
              </div>
              <div className="fc-stat">
                <span className="fc-label">兵</span>
                <span className="fc-value">{fs.troops.toLocaleString()}</span>
              </div>
              <div className="fc-stat">
                <span className="fc-label">粮</span>
                <span className="fc-value ink-dim">—</span>
              </div>
            </div>
            {agent && (
              <div className="fc-agent">
                {agent.name} · {agent.mode === 'managed' ? '托管' : '玩家'}
                {agent.submitted && <span className="fc-submitted"> ✓已提交</span>}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

// ── Event feed ──────────────────────────────────
function EventFeed({ events }) {
  const [expanded, setExpanded] = useState(null)
  const [locked, setLocked] = useState(false)
  const bottomRef = useRef(null)

  useEffect(() => {
    if (!locked && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [events, locked])

  const displayEvents = events || []

  return (
    <div className="event-feed">
      <div className="event-feed-header">
        <span>事件流</span>
        <button className={`btn-lock ${locked ? 'locked' : ''}`}
          onClick={() => setLocked(!locked)}>
          {locked ? '已锁定' : '自动滚动'}
        </button>
      </div>
      <div className="event-feed-body">
        {displayEvents.length === 0 && (
          <div className="event-empty">暂无事件，等待战局推进…</div>
        )}
        {displayEvents.map((evt, i) => {
          const isExpanded = expanded === i
          const result = evt.result || evt.type || '?'
          const captured = evt.captured_by
          const defended = evt.defended_by
          return (
            <div key={i} className={`event-item ${isExpanded ? 'expanded' : ''}`}
              onClick={() => setExpanded(isExpanded ? null : i)}>
              <div className="event-summary">
                <span className="event-tick">T{evt.tick ?? '?'}</span>
                <span className="event-desc">
                  {evt.city || '?'}
                  {' · '}
                  {result === 'captured' && captured
                    ? <span style={{ color: FACTION_COLORS[captured] || '#fff' }}>{captured}攻占</span>
                    : result === 'defended' && defended
                    ? <span style={{ color: FACTION_COLORS[defended] || '#fff' }}>{defended}守住</span>
                    : result}
                </span>
              </div>
              {isExpanded && evt.combat_report && (
                <div className="event-combat-report">
                  <div className="cr-grid">
                    <div>攻方兵力: {evt.combat_report.attacker_troops_committed}</div>
                    <div>攻方伤亡: {Math.round((evt.combat_report.attacker_casualty_pct || 0) * 100)}%</div>
                    <div>守方兵力: {evt.combat_report.defender_troops}</div>
                    <div>守方伤亡: {Math.round((evt.combat_report.defender_casualty_pct || 0) * 100)}%</div>
                    <div>城防等级: Lv{evt.combat_report.defender_defense_level ?? 0}</div>
                    <div>收编降卒: {evt.combat_report.defender_troops_integrated ?? '—'}</div>
                  </div>
                  {evt.dayan_hexagram && (
                    <div className="cr-hexagram">
                      卦象: {evt.dayan_hexagram.main} → {evt.dayan_hexagram.changed}
                    </div>
                  )}
                </div>
              )}
            </div>
          )
        })}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}

// ── Narrative panel ─────────────────────────────
function NarrativePanel({ chapters }) {
  const [locked, setLocked] = useState(false)
  const bottomRef = useRef(null)

  useEffect(() => {
    if (!locked && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [chapters, locked])

  const displayChapters = chapters || []

  return (
    <div className="panel narrative-panel">
      <div className="event-feed-header">
        <span>评书叙事</span>
        <button className={`btn-lock ${locked ? 'locked' : ''}`}
          onClick={() => setLocked(!locked)}>
          {locked ? '已锁定' : '自动滚动'}
        </button>
      </div>
      <div className="event-feed-body" style={{ maxHeight: 360 }}>
        {displayChapters.length === 0 && (
          <div className="narrative-placeholder">评书正在生成…</div>
        )}
        {displayChapters.map((ch, i) => (
          <div key={i} className="narrative-chapter">
            <div className="narrative-chapter-tick">
              Tick {ch.tick_start}-{ch.tick_end}
            </div>
            <div className="narrative-chapter-text">{ch.content}</div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}

// ── Win rate curve ──────────────────────────────
function WinRateCurve({ history }) {
  const h = history || []
  if (h.length < 2) return null

  const W = 280, H = 80, pad = { top: 8, right: 8, bottom: 16, left: 8 }
  const iw = W - pad.left - pad.right
  const ih = H - pad.top - pad.bottom

  function linePath(faction) {
    if (h.length < 1) return ''
    const points = h.map((pt, i) => {
      const x = pad.left + (i / Math.max(h.length - 1, 1)) * iw
      const total = (pt.蜀 || 1) + (pt.魏 || 1) + (pt.吴 || 1)
      const ratio = (pt[faction] || 0) / total
      const y = pad.top + (1 - ratio) * ih
      return `${i === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${y.toFixed(1)}`
    })
    return points.join(' ')
  }

  return (
    <div className="panel winrate-panel">
      <div className="panel-title">胜率曲线</div>
      <svg viewBox={`0 0 ${W} ${H}`} className="winrate-svg">
        {/* Grid lines */}
        {[0.25, 0.5, 0.75].map(r => (
          <line key={r} x1={pad.left} y1={pad.top + r * ih}
            x2={W - pad.right} y2={pad.top + r * ih}
            stroke="var(--line)" strokeWidth={0.5} />
        ))}
        {FACTIONS.map(f => (
          <path key={f} d={linePath(f)} fill="none"
            stroke={FACTION_COLORS[f]} strokeWidth={1.5}
            strokeLinejoin="round" />
        ))}
      </svg>
      <div className="winrate-legend">
        {FACTIONS.map(f => (
          <span key={f} style={{ color: FACTION_COLORS[f] }}>━ {f}</span>
        ))}
      </div>
    </div>
  )
}

// ── Tick progress bar ───────────────────────────
function TickBar({ tick, maxTicks }) {
  const pct = maxTicks ? Math.round((tick / maxTicks) * 100) : 0
  return (
    <div className="tick-bar-wrap">
      <div className="tick-bar-label">Tick {tick ?? 0}/{maxTicks ?? 50}</div>
      <div className="tick-bar">
        <div className="tick-bar-fill" style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

// ── Main component ──────────────────────────────
export default function SpectateV2() {
  const [params] = useSearchParams()
  const gameId = params.get('game')

  const [pollInterval, setPollInterval] = useState(3000)
  const { data, error, isLoading } = usePolling('/v1/lobby/status', { intervalMs: pollInterval })

  // Adapt polling interval to game status
  useEffect(() => {
    if (!data?.status) return
    const next = data.status === 'finished' ? null
      : data.status === 'countdown' ? 1000
      : 3000
    setPollInterval(prev => prev === next ? prev : next)
  }, [data?.status])

  // Agent details change slowly — poll at 10s
  const { data: cgData } = usePolling('/current-game', { intervalMs: 10000 })

  // Accumulate power history for win rate curve
  const [powerHistory, setPowerHistory] = useState([])
  const lastTickRef = useRef(-1)

  useEffect(() => {
    if (!data?.cities) return
    const tick = data.tick
    if (tick === lastTickRef.current) return
    lastTickRef.current = tick

    const factions = computeFactions(data.cities)
    const power = {}
    for (const f of FACTIONS) {
      // Power = cities * 3 + troops * 0.001 + grain * 0.0005
      power[f] = (factions[f]?.cities || 0) * 3 + (factions[f]?.troops || 0) * 0.001
    }
    setPowerHistory(prev => {
      const next = [...prev, { tick, ...power }]
      // Keep last 50 data points
      return next.slice(-50)
    })
  }, [data?.tick, data?.cities])

  if (isLoading && !data) {
    return <div className="page"><p>加载中…</p></div>
  }

  if (error) console.error('SpectateV2 fetch error:', error)

  const tick = data?.tick ?? 0
  const maxTicks = data?.max_ticks ?? 50
  const status = data?.status ?? '?'
  const cities = data?.cities || []
  const events = data?.events || []
  const chapters = data?.chapters || []
  const agents = cgData?.agents || []

  return (
    <div className="page spectate-page">
      {error && <div className="error-banner">Failed to fetch: {error}</div>}

      {/* ── Top bar ───────────────────────────── */}
      <div className="spectate-topbar">
        <h1>
          Game <span className="game-id">#{data?.game_id ?? '?'}</span>
          {' · '}Tick <span className="tick-num">{tick}</span>/{maxTicks}
        </h1>
        <span className={`status-tag status-${status}`}>{status}</span>
      </div>

      {/* ── Main layout: map + eval + factions | narrative ── */}
      <div className="spectate-main">
        <div className="spectate-left">
          {/* City map */}
          <div className="panel map-panel">
            <div className="panel-title">战局地图</div>
            <CityMap cities={cities} events={events} />
          </div>

          {/* Eval bar */}
          <EvalBar cities={cities} />

          {/* Faction cards */}
          <FactionCards cities={cities} agents={agents} />

          {/* Win rate curve */}
          <WinRateCurve history={powerHistory} />
        </div>

        <div className="spectate-right">
          {/* Narrative stream */}
          <NarrativePanel chapters={chapters} />
        </div>
      </div>

      {/* ── Event feed ────────────────────────── */}
      <EventFeed events={events} />

      {/* ── Tick progress ─────────────────────── */}
      <TickBar tick={tick} maxTicks={maxTicks} />
    </div>
  )
}
