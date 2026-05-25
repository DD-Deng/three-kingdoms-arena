import { useState, useEffect, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import { api } from '../api'
import { FACTION_COLORS, FACTION_MONARCHS } from '../constants'

// ── localStorage helpers ───────────────────────────
const LS_KEY = 'arena_sessions'

function loadSessions() {
  try { return JSON.parse(localStorage.getItem(LS_KEY) || '{}') }
  catch { return {} }
}

function saveSession(faction, data) {
  const sessions = loadSessions()
  sessions[faction] = data
  localStorage.setItem(LS_KEY, JSON.stringify(sessions))
}

// Cache instruction text in localStorage so re-open doesn't need fetch
function saveInstructionToLocal(faction, text) {
  const sessions = loadSessions()
  if (sessions[faction]) {
    sessions[faction].instruction = text
    localStorage.setItem(LS_KEY, JSON.stringify(sessions))
  }
}

function getSession(faction) {
  return loadSessions()[faction] || null
}

// ── Components ─────────────────────────────────────
function CopyButton({ text, label, copiedLabel }) {
  const [copied, setCopied] = useState(false)

  const doCopy = () => {
    if (!text) return
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }).catch(() => {
      const ta = document.createElement('textarea')
      ta.value = text
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  return (
    <button className={copied ? 'btn-copied' : 'btn-primary jm-copy-btn'}
      onClick={doCopy} disabled={!text}>
      {copied ? (copiedLabel || '✓ 已复制') : (label || '📋 复制')}
    </button>
  )
}

// ── Main modal ─────────────────────────────────────
export default function JoinModal({ faction, gameId, onClose, initialPhase, preResult }) {
  const [phase, setPhase] = useState(initialPhase || 'confirm')
  const [result, setResult] = useState(preResult || null)
  const [instruction, setInstruction] = useState(null)
  const [error, setError] = useState('')
  const [collapsed, setCollapsed] = useState(true)

  const monarch = FACTION_MONARCHS[faction]
  // result.token matches localStorage saveSession; result.session_token matches fresh join API response
  const tokenValue = result?.session_token || result?.token
  const savedInstruction = result?.instruction

  function cacheInstruction(text) { saveInstructionToLocal(faction, text) }

  // Auto-fetch or use cached instruction
  useEffect(() => {
    if (phase !== 'done' || !result || instruction) return
    if (savedInstruction) { setInstruction(savedInstruction); return }
    if (!tokenValue) return
    let cancelled = false
    fetch(`/v1/lobby/instruction?token=${encodeURIComponent(tokenValue)}`)
      .then(async r => {
        const text = await r.text()
        if (!r.ok) {
          try { const err = JSON.parse(text); return { error: err.detail || `HTTP ${r.status}` } }
          catch { return { error: `HTTP ${r.status}` } }
        }
        return { text }
      })
      .then(result => {
        if (cancelled) return
        if (result.error) setInstruction(`__ERROR__${result.error}`)
        else { setInstruction(result.text); cacheInstruction(result.text) }
      })
      .catch(() => {})
    return () => { cancelled = true }
  }, [phase, result, instruction, tokenValue, savedInstruction])

  // Auto-join on confirm
  useEffect(() => {
    if (phase !== 'loading') return
    let cancelled = false

    ;(async () => {
      try {
        const res = await api.joinLobby(faction)
        if (cancelled) return
        setResult(res)

        // Save to localStorage immediately (before instruction fetch)
        // so token survives even if instruction fetch fails
        saveSession(faction, {
          token: res.session_token,
          game_id: res.game_id || gameId,
          expires_at: res.expires_at,
        })
        // Fetch instruction
        try {
          const instUrl = `/v1/lobby/instruction?token=${encodeURIComponent(res.session_token)}`
          const resp = await fetch(instUrl)
          const text = await resp.text()
          if (!cancelled) {
            setInstruction(text)
            saveInstructionToLocal(faction, text)
            setPhase('done')
          }
        } catch {
          if (!cancelled) {
            setInstruction(null)
            setPhase('done')
          }
        }
      } catch (e) {
        if (cancelled) return
        if (e.code === 'COUNTDOWN_STARTED') setError('倒计时已启动，无法加入')
        else setError(e.message || '加入失败')
        setPhase('error')
      }
    })()

    return () => { cancelled = true }
  }, [phase === 'loading'])

  const onOverlayClick = (e) => { if (e.target === e.currentTarget) onClose() }

  return (
    <div className="jm-overlay" onClick={onOverlayClick}>
      <div className="jm-box">
        <button className="jm-close" onClick={onClose}>✕</button>

        {/* ── Phase: confirm ─────────────────────── */}
        {phase === 'confirm' && (
          <div className="jm-body">
            <div className="jm-icon" style={{ color: FACTION_COLORS[faction] }}>⚔</div>
            <h2 className="jm-title" style={{ color: FACTION_COLORS[faction] }}>
              确认加入 {faction} · {monarch}
            </h2>
            <p className="jm-hint">
              确认后，你将获得一段"接入指令"。复制并粘贴给你的 agent，它就会自动接入对局。
            </p>
            <div className="jm-actions">
              <button className="btn-ghost" onClick={onClose}>取消</button>
              <button className="btn-primary" onClick={() => setPhase('loading')}>
                确认加入 ⚔
              </button>
            </div>
          </div>
        )}

        {/* ── Phase: loading ──────────────────────── */}
        {phase === 'loading' && (
          <div className="jm-body jm-center">
            <div className="jm-spinner" />
            <p className="jm-loading-text">正在接入服务器…</p>
          </div>
        )}

        {/* ── Phase: error ────────────────────────── */}
        {phase === 'error' && (
          <div className="jm-body">
            <div className="jm-icon" style={{ color: 'var(--accent)' }}>⚠</div>
            <h2 className="jm-title">加入失败</h2>
            <p className="jm-error-text">{error}</p>
            <div className="jm-actions">
              <button className="btn-ghost" onClick={onClose}>关闭</button>
              <button className="btn-primary" onClick={() => { setPhase('confirm'); setError('') }}>重试</button>
            </div>
          </div>
        )}

        {/* ── Phase: done ─────────────────────────── */}
        {phase === 'done' && result && (
          <div className="jm-body jm-done">
            {/* a) Success header */}
            <div className="jm-done-header">
              <span className="jm-done-check">✓</span>
              <h2 style={{ color: FACTION_COLORS[faction], margin: 0 }}>
                你已加入 {faction} 阵营
              </h2>
            </div>
            <p className="jm-done-sub">
              Session Token · 仅本局有效
            </p>

            {/* b) Token card */}
            <div className="jm-token-card">
              <span className="jm-token-label">Session Token</span>
              <code className="jm-token-value">{tokenValue}</code>
              <CopyButton text={tokenValue} label="📋 复制 Token" copiedLabel="✓ 已复制" />
            </div>

            {/* c) Collapsible full instruction */}
            <div className="jm-instruction-section">
              <div className="jm-inst-header">
                <span className="jm-inst-title">完整接入指令</span>
                <button className="jm-inst-toggle" onClick={() => setCollapsed(!collapsed)}>
                  {collapsed ? '展开 ▼' : '收起 ▲'}
                </button>
                <CopyButton text={instruction} label="📋 复制全部" copiedLabel="✓ 已复制" />
              </div>
              {!collapsed && (
                <div className="jm-inst-body">
                  {instruction && instruction.startsWith('__ERROR__') ? (
                    <div className="jm-inst-error">
                      {instruction.replace('__ERROR__', '')}
                      <br />Token: <code>{tokenValue}</code>
                    </div>
                  ) : instruction ? (
                    <ReactMarkdown>{instruction}</ReactMarkdown>
                  ) : (
                    <div className="jm-inst-error">
                      指令加载失败，token 已生效，请联系管理员或刷新重试。
                      <br />Token: <code>{tokenValue}</code>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* d) Footer */}
            <div className="jm-actions">
              <button className="btn-ghost" onClick={onClose}>关闭</button>
              <span className="jm-footer-hint">关闭后可在大厅页对应阵营卡上重新查看</span>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Re-exports for external use ────────────────────
export { loadSessions, saveSession, getSession }
