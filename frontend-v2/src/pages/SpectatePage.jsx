import { useState, useRef, useEffect } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import usePolling from '../hooks/usePolling'
import { FACTIONS, FACTION_COLORS, FACTION_MONARCHS, CITY_POSITIONS, ADJACENCY } from '../constants'

function computeFactions(cities) {
  const factions = { 蜀: { cities: 0, troops: 0 }, 魏: { cities: 0, troops: 0 }, 吴: { cities: 0, troops: 0 } }
  if (!cities) return factions
  for (const c of cities) {
    if (c.owner && factions[c.owner]) { factions[c.owner].cities += 1; factions[c.owner].troops += c.troops || 0 }
  }
  return factions
}

function computeEvalPower(cities) {
  const factions = computeFactions(cities)
  const power = {}
  for (const f of FACTIONS) power[f] = factions[f].cities * 3 + factions[f].troops * 0.001
  const total = power.蜀 + power.魏 + power.吴 || 1
  for (const f of FACTIONS) power[f] = Math.round((power[f] / total) * 100)
  return power
}

function CityMap({ cities, events }) {
  const [flashes, setFlashes] = useState({})
  const [arrows, setArrows] = useState([])
  const prevLenRef = useRef(0)
  const didInitRef = useRef(false)

  useEffect(() => {
    if (!events || events.length === 0) return
    if (!didInitRef.current) {
      prevLenRef.current = events.length
      didInitRef.current = true
      return
    }
    const newEvents = events.slice(prevLenRef.current)
    prevLenRef.current = events.length
    for (const evt of newEvents) {
      const city = evt.city
      if (!city) continue
      const result = evt.result
      if (result !== 'captured' && result !== 'defended') continue
      setFlashes(prev => ({ ...prev, [city]: true }))
      setTimeout(() => setFlashes(prev => ({ ...prev, [city]: false })), 1200)
      const attacker = evt.captured_by || evt.attackers?.[0]
      if (attacker && cities) {
        for (const [a, b] of ADJACENCY) {
          let srcName = null
          if (a === city) srcName = b; else if (b === city) srcName = a
          if (!srcName) continue
          const srcCity = cities.find(c => c.name === srcName)
          if (srcCity && srcCity.owner === attacker) {
            const arrow = { from: srcName, to: city, faction: attacker }
            setArrows(prev => [...prev, arrow])
            setTimeout(() => setArrows(prev => prev.filter(x => x !== arrow)), 2000)
            break
          }
        }
      }
    }
  }, [events, cities])

  const cityMap = {}
  if (cities) for (const c of cities) cityMap[c.name] = c

  return (
    <svg viewBox="0 0 300 260" className="sp-map-svg">
      {ADJACENCY.map(([a, b]) => {
        const pa = CITY_POSITIONS[a], pb = CITY_POSITIONS[b]
        return <line key={`${a}-${b}`} x1={pa.x} y1={pa.y} x2={pb.x} y2={pb.y} className="sp-map-adj" />
      })}
      {Object.entries(CITY_POSITIONS).map(([name, pos]) => {
        const c = cityMap[name]
        const owner = c?.owner; const troops = c?.troops ?? '?'
        const color = FACTION_COLORS[owner] || 'var(--ink-mute)'
        const flash = flashes[name]
        return (
          <g key={name} className={`sp-map-city ${flash ? 'sp-map-city-flash' : ''}`}>
            <rect x={pos.x - 28} y={pos.y - 14} width={56} height={28} rx={6}
              fill="var(--panel)" stroke={color} strokeWidth={1.5} />
            <text x={pos.x} y={pos.y - 1} textAnchor="middle" fill={color} fontSize={11} fontWeight={600}>{name}</text>
            <text x={pos.x} y={pos.y + 12} textAnchor="middle" fill={color} fontSize={10} fontFamily="var(--font-mono)">
              {owner || '—'} {troops}
            </text>
          </g>
        )
      })}
      {arrows.map((a, i) => {
        const from = CITY_POSITIONS[a.from], to = CITY_POSITIONS[a.to]
        if (!from || !to) return null
        return <line key={i} x1={from.x} y1={from.y} x2={to.x} y2={to.y}
          className="sp-map-arrow" stroke={FACTION_COLORS[a.faction] || '#888'} strokeWidth={2} markerEnd="url(#sp-arrowhead)" />
      })}
      <defs>
        <marker id="sp-arrowhead" markerWidth={8} markerHeight={6} refX={8} refY={3} orient="auto">
          <polygon points="0 0, 8 3, 0 6" fill="#888" />
        </marker>
      </defs>
    </svg>
  )
}

function EvalBar({ cities }) {
  const power = computeEvalPower(cities)
  return (
    <div className="sp-eval-wrap">
      <div className="sp-eval-bar">
        {FACTIONS.map(f => <div key={f} className="sp-eval-seg" style={{ width: `${power[f]}%`, background: FACTION_COLORS[f] }} title={`${f}: ${power[f]}%`} />)}
      </div>
      <div className="sp-eval-labels">
        {FACTIONS.map(f => <span key={f} style={{ color: FACTION_COLORS[f] }}>{f} {power[f]}%</span>)}
      </div>
    </div>
  )
}

function FactionCards({ cities, agents, factionsData }) {
  const factions = computeFactions(cities)
  const agentMap = {}
  if (agents) for (const a of agents) agentMap[a.faction] = a
  return (
    <div className="sp-fc-row">
      {FACTIONS.map(f => {
        const fs = factions[f]; const agent = agentMap[f]
        const grain = factionsData?.[f]?.grain
        return (
          <div key={f} className="sp-fc-card" style={{ borderLeft: `3px solid ${FACTION_COLORS[f]}` }}>
            <div className="sp-fc-header">
              <span className="sp-fc-faction" style={{ color: FACTION_COLORS[f] }}>{f}</span>
              <span className="sp-fc-monarch">{FACTION_MONARCHS[f]}</span>
            </div>
            <div className="sp-fc-stats">
              <div className="sp-fc-stat"><span className="sp-fc-label">城</span><span className="sp-fc-value">{fs.cities}</span></div>
              <div className="sp-fc-stat"><span className="sp-fc-label">兵</span><span className="sp-fc-value">{fs.troops.toLocaleString()}</span></div>
              <div className="sp-fc-stat"><span className="sp-fc-label">粮</span><span className="sp-fc-value">{grain != null ? grain.toLocaleString() : '—'}</span></div>
            </div>
            {agent && (
              <div className="sp-fc-agent">{agent.name} · {agent.mode === 'managed' ? '托管' : '玩家'}</div>
            )}
          </div>
        )
      })}
    </div>
  )
}

function EventFeed({ events }) {
  const [expanded, setExpanded] = useState(null)
  const [locked, setLocked] = useState(false)
  const [newIds, setNewIds] = useState(new Set())
  const bodyRef = useRef(null)
  const prevLenRef = useRef(0)

  useEffect(() => { if (!locked && bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight }, [events, locked])

  useEffect(() => {
    if (!events) return
    const prevLen = prevLenRef.current; prevLenRef.current = events.length
    if (events.length <= prevLen) return
    const fresh = new Set()
    for (let i = prevLen; i < events.length; i++) fresh.add(i)
    setNewIds(fresh)
    const timer = setTimeout(() => setNewIds(new Set()), 500)
    return () => clearTimeout(timer)
  }, [events])

  const displayEvents = events || []
  return (
    <div className="sp-feed">
      <div className="sp-feed-header">
        <span>事件流</span>
        <button className={`sp-feed-lock ${locked ? 'locked' : ''}`} onClick={() => setLocked(!locked)}>{locked ? '已锁定' : '自动滚动'}</button>
      </div>
      <div className="sp-feed-body" ref={bodyRef}>
        {displayEvents.length === 0 && <div className="sp-feed-empty">暂无事件，等待战局推进…</div>}
        {displayEvents.map((evt, i) => {
          const isExpanded = expanded === i
          const result = evt.result || evt.type || '?'
          const captured = evt.captured_by; const defended = evt.defended_by
          return (
            <div key={i} className={`sp-event ${isExpanded ? 'expanded' : ''} ${newIds.has(i) ? 'sp-event-new' : ''}`}
              onClick={() => setExpanded(isExpanded ? null : i)}>
              <div className="sp-event-summary">
                <span className="sp-event-tick">T{evt.tick ?? '?'}</span>
                <span className="sp-event-desc">
                  {evt.text ? evt.text
                    : <>{evt.city || '?'}{' · '}
                      {result === 'captured' && captured ? <span style={{ color: FACTION_COLORS[captured] || 'var(--ink)' }}>{captured}攻占</span>
                        : result === 'defended' && defended ? <span style={{ color: FACTION_COLORS[defended] || 'var(--ink)' }}>{defended}守住</span>
                        : result}</>
                  }
                </span>
              </div>
              {isExpanded && evt.combat_report && (
                <div className="sp-cr">
                  <div className="sp-cr-grid">
                    <div>攻方兵力: {evt.combat_report.attacker_troops_committed}</div>
                    <div>攻方伤亡: {Math.round((evt.combat_report.attacker_casualty_pct || 0) * 100)}%</div>
                    <div>守方兵力: {evt.combat_report.defender_troops}</div>
                    <div>守方伤亡: {Math.round((evt.combat_report.defender_casualty_pct || 0) * 100)}%</div>
                    <div>城防等级: Lv{evt.combat_report.defender_defense_level ?? 0}</div>
                    <div>收编降卒: {evt.combat_report.defender_troops_integrated ?? '—'}</div>
                  </div>
                  {evt.dayan_hexagram && <div className="sp-cr-hexagram">卦象: {evt.dayan_hexagram.main} → {evt.dayan_hexagram.changed}</div>}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function NarrativePanel({ chapters }) {
  const [locked, setLocked] = useState(false)
  const bodyRef = useRef(null)
  useEffect(() => { if (!locked && bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight }, [chapters, locked])
  const displayChapters = chapters || []
  return (
    <div className="sp-panel sp-narrative">
      <div className="sp-feed-header">
        <span>评书叙事</span>
        <button className={`sp-feed-lock ${locked ? 'locked' : ''}`} onClick={() => setLocked(!locked)}>{locked ? '已锁定' : '自动滚动'}</button>
      </div>
      <div className="sp-feed-body" style={{ maxHeight: 360 }} ref={bodyRef}>
        {displayChapters.length === 0 && <div className="sp-narrative-placeholder">评书正在生成…</div>}
        {displayChapters.map((ch, i) => (
          <div key={i} className="sp-narrative-chapter">
            <div className="sp-narrative-tick">Tick {ch.tick_start}-{ch.tick_end}</div>
            <div className="sp-narrative-text">{ch.content}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

function WinRateCurve({ history }) {
  const h = history || []
  if (h.length < 2) return null
  const W = 280, H = 80, pad = { top: 8, right: 8, bottom: 16, left: 8 }
  const iw = W - pad.left - pad.right; const ih = H - pad.top - pad.bottom
  function linePath(faction) {
    if (h.length < 1) return ''
    return h.map((pt, i) => {
      const x = pad.left + (i / Math.max(h.length - 1, 1)) * iw
      const total = (pt.蜀 || 1) + (pt.魏 || 1) + (pt.吴 || 1)
      const y = pad.top + (1 - (pt[faction] || 0) / total) * ih
      return `${i === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${y.toFixed(1)}`
    }).join(' ')
  }
  return (
    <div className="sp-panel sp-winrate">
      <div className="sp-panel-title">胜率曲线</div>
      <svg viewBox={`0 0 ${W} ${H}`} className="sp-winrate-svg">
        {[0.25, 0.5, 0.75].map(r => <line key={r} x1={pad.left} y1={pad.top + r * ih} x2={W - pad.right} y2={pad.top + r * ih} stroke="var(--line)" strokeWidth={0.5} />)}
        {FACTIONS.map(f => <path key={f} d={linePath(f)} fill="none" stroke={FACTION_COLORS[f]} strokeWidth={1.5} strokeLinejoin="round" />)}
      </svg>
      <div className="sp-winrate-legend">{FACTIONS.map(f => <span key={f} style={{ color: FACTION_COLORS[f] }}>━ {f}</span>)}</div>
    </div>
  )
}

function TickBar({ tick, maxTicks }) {
  const pct = maxTicks ? Math.round((tick / maxTicks) * 100) : 0
  return (
    <div className="sp-tickbar-wrap">
      <div className="sp-tickbar-label">Tick {tick ?? 0}/{maxTicks ?? 50}</div>
      <div className="sp-tickbar"><div className="sp-tickbar-fill" style={{ width: `${pct}%` }} /></div>
    </div>
  )
}

// ── Main component ─────────────────────────────────
export default function SpectatePage() {
  const [params] = useSearchParams()
  const gameIdFromUrl = params.get('game') ? parseInt(params.get('game'), 10) : null
  const [resolvedGameId, setResolvedGameId] = useState(gameIdFromUrl)

  // Live state from status (has troops/defense that replay lacks)
  const [pollInterval, setPollInterval] = useState(3000)
  const { data: liveData, error: liveError } = usePolling('/v1/lobby/status', { intervalMs: pollInterval })
  const liveIsLoading = !liveData && !liveError

  // Event history from replay (complete, no client accumulation)
  const [replayData, setReplayData] = useState(null)
  const [eventError, setEventError] = useState(null)

  // Resolve gameId for replay: URL param priority, otherwise from live status
  useEffect(() => {
    if (resolvedGameId != null) return
    if (!liveData?.game_id) return
    setResolvedGameId(liveData.game_id)
  }, [liveData?.game_id, resolvedGameId])

  // Adjust status poll interval from live status
  useEffect(() => {
    if (!liveData?.status) return
    const next = liveData.status === 'finished' ? null : liveData.status === 'countdown' ? 1000 : 3000
    setPollInterval(prev => prev === next ? prev : next)
  }, [liveData?.status])

  // Poll replay endpoint for event history
  useEffect(() => {
    if (resolvedGameId == null) return
    let cancelled = false
    let timer = null

    async function poll() {
      try {
        const r = await fetch(`/v1/games/${resolvedGameId}/replay`)
        if (!r.ok) { if (!cancelled) setEventError(`HTTP ${r.status}`); return }
        const d = await r.json()
        if (cancelled) return
        setReplayData(d)
        if (d.status === 'finished' && timer) { clearInterval(timer); timer = null }
      } catch (e) {
        if (!cancelled) setEventError(e.message)
      }
    }

    poll()
    timer = setInterval(poll, 3000)
    return () => { cancelled = true; if (timer) clearInterval(timer) }
  }, [resolvedGameId])

  // Flatten events from all ticks with tick injection
  const flatEvents = (replayData?.ticks || []).flatMap(entry =>
    (entry.events || []).map(evt => ({ ...evt, tick: evt.tick ?? entry.tick }))
  )

  // Power history from replay ticks (cities per tick for win rate curve)
  const powerHistory = (replayData?.ticks || []).map(entry => {
    const factions = computeFactions(entry.cities || [])
    const power = {}
    for (const f of FACTIONS) power[f] = (factions[f]?.cities || 0) * 3 + (factions[f]?.troops || 0) * 0.001
    return { tick: entry.tick, ...power }
  })

  if (liveIsLoading && !liveData) return <div className="sp-loading">加载中…</div>

  // Live state from status (has troops for map, cards, eval bar)
  const tick = liveData?.tick ?? 0
  const maxTicks = liveData?.max_ticks ?? 50
  const status = liveData?.status ?? '?'
  const cities = liveData?.cities || []
  const chapters = liveData?.chapters || []
  const agents = replayData?.agents || []
  const factionsData = liveData?.factions || {}

  const isWaiting = status === 'lobby' && tick === 0

  if (isWaiting) {
    return (
      <div className="sp-page">
        <div className="sp-topbar">
          <h1>观战</h1>
          <Link to="/" className="sp-back">← 返回大厅</Link>
        </div>
        <div className="placeholder-page" style={{ marginTop: 60 }}>
          <h1>对局即将开始</h1>
          <p>等待 AI 入场…</p>
        </div>
      </div>
    )
  }

  return (
    <div className="sp-page">
      {(liveError || eventError) && <div className="sp-error">Failed to fetch: {liveError || eventError}</div>}
      <div className="sp-topbar">
        <h1>Game <span className="sp-mono">{liveData?.game_id ?? '?'}</span>{' · '}Tick <span className="sp-mono">{tick}</span>/{maxTicks}</h1>
        <span className={`sp-status sp-st-${status}`}>{status}</span>
        <Link to="/" className="sp-back">← 返回大厅</Link>
      </div>

      <div className="sp-main">
        <div className="sp-left">
          <div className="sp-panel sp-map-panel">
            <div className="sp-panel-title">战局地图</div>
            <CityMap key={resolvedGameId} cities={cities} events={flatEvents} />
          </div>
          <EvalBar cities={cities} />
          <FactionCards cities={cities} agents={agents} factionsData={factionsData} />
          <WinRateCurve history={powerHistory} />
        </div>
        <div className="sp-right">
          <NarrativePanel chapters={chapters} />
        </div>
      </div>

      <EventFeed events={flatEvents} />
      <TickBar tick={tick} maxTicks={maxTicks} />
    </div>
  )
}
