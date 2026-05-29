import { useState, useEffect, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import { api } from '../api'
import { FACTION_COLORS, FACTION_MONARCHS } from '../constants'

// ── localStorage helpers ───────────────────────────
const LS_KEY = 'arena_sessions'
const LS_API_KEY = 'arena_api_key'

function loadSessions() {
  try { return JSON.parse(localStorage.getItem(LS_KEY) || '{}') }
  catch { return {} }
}

function loadSavedApiKey() {
  try { return localStorage.getItem(LS_API_KEY) || '' }
  catch { return '' }
}

function saveApiKey(key) {
  try { localStorage.setItem(LS_API_KEY, key) }
  catch {}
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
export default function JoinModal({ faction, gameId, gameStatus, factionCityCount, onClose, initialPhase, preResult, onLeave, slotReady }) {
  const [phase, setPhase] = useState(initialPhase || 'confirm')
  const [result, setResult] = useState(preResult || null)
  const [instruction, setInstruction] = useState(null)
  const [error, setError] = useState('')
  const [collapsed, setCollapsed] = useState(true)
  const [confirmLeave, setConfirmLeave] = useState(false)
  const [leaving, setLeaving] = useState(false)
  const [apiKey, setApiKey] = useState(loadSavedApiKey)
  const [showReg, setShowReg] = useState(false)
  const [regName, setRegName] = useState('')
  const [regDesc, setRegDesc] = useState('')
  const [regLoading, setRegLoading] = useState(false)
  const [regResult, setRegResult] = useState(null)
  const [regError, setRegError] = useState('')

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
        const res = await api.joinLobby(faction, apiKey || undefined)
        if (cancelled) return
        setResult(res)

        // Save api_key to localStorage on successful join
        if (apiKey) saveApiKey(apiKey)

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
        if (e.status === 401 && e.message && e.message.includes('Agent ID')) setError('Agent ID 无效，请检查或重新注册')
        else if (e.code === 'COUNTDOWN_STARTED') setError('倒计时已启动，无法加入')
        else setError(e.message || '加入失败')
        setPhase('error')
      }
    })()

    return () => { cancelled = true }
  }, [phase === 'loading'])

  const onOverlayClick = (e) => { if (e.target === e.currentTarget) onClose() }

  async function doRegister() {
    if (!regName.trim()) { setRegError('名字不能为空'); return }
    setRegLoading(true)
    setRegError('')
    setRegResult(null)
    try {
      const r = await fetch('/v1/profile/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ display_name: regName.trim(), description: regDesc.trim() || undefined }),
      })
      const data = await r.json()
      if (!r.ok) { setRegError(data.detail || '注册失败'); setRegLoading(false); return }
      setRegResult(data)
      setApiKey(data.api_key)
      saveApiKey(data.api_key)
      setRegLoading(false)
    } catch {
      setRegError('网络错误，请重试')
      setRegLoading(false)
    }
  }

  // ── Leave button logic ──────────────────────────────
  const status = gameStatus || ''
  const cityCount = factionCityCount ?? -1
  const canLeave = result && tokenValue && gameId
  const isEliminated = cityCount === 0
  const isAlive = cityCount > 0
  const inLobby = status === 'lobby' || status === 'countdown'
  const inGame = status === 'active' || status === 'paused'

  let leaveLabel = '退出'
  let leaveNeedsConfirm = false
  if (inLobby) { leaveLabel = '取消加入'; leaveNeedsConfirm = false }
  else if (inGame && isAlive) { leaveLabel = '放弃对局'; leaveNeedsConfirm = true }
  else if (inGame && isEliminated) { leaveLabel = '退出查看战报'; leaveNeedsConfirm = true }

  function doLeave() {
    if (!canLeave) return
    setLeaving(true)
    fetch(`/v1/games/${gameId}/leave?token=${encodeURIComponent(tokenValue)}`, { method: 'POST' })
      .then(async r => {
        if (!r.ok) {
          if (r.status === 401 || r.status === 410) {
            localStorage.removeItem('arena_sessions')
            alert('Token 已失效，页面将刷新')
            window.location.reload()
            return null
          }
          const t = await r.text(); try { const j = JSON.parse(t); setError(j.detail || `HTTP ${r.status}`) } catch { setError(`HTTP ${r.status}`) }; return null
        }
        return r.json()
      })
      .then(data => {
        if (!data) { setLeaving(false); return }
        // Clear localStorage for this faction
        try {
          const sessions = JSON.parse(localStorage.getItem('arena_sessions') || '{}')
          delete sessions[faction]
          localStorage.setItem('arena_sessions', JSON.stringify(sessions))
        } catch {}
        setLeaving(false)
        setConfirmLeave(false)
        if (onLeave) onLeave(data)
        else if (data.redirect_to) { window.location.href = data.redirect_to }
      })
      .catch(() => setLeaving(false))
  }

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
            <div className="jm-apikey-row">
              <label className="jm-apikey-label" htmlFor="jm-apikey">
                Agent ID 密钥（可选，登榜用）
              </label>
              <input
                id="jm-apikey"
                className="jm-apikey-input"
                type="text"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="注册后获得的密钥，粘贴到这里"
                autoComplete="off"
              />
              <span className="jm-apikey-link" onClick={() => setShowReg(!showReg)}>
                还没有 Agent ID？注册一个 →
              </span>
            </div>

            {/* ── Inline registration form ─────────── */}
            {showReg && (
              <div className="jm-reg-box">
                {!regResult ? (
                  <>
                    <div className="jm-reg-row">
                      <label className="jm-apikey-label" htmlFor="jm-reg-name">Agent ID 名字（必填，榜上显示）</label>
                      <input
                        id="jm-reg-name"
                        className="jm-apikey-input"
                        type="text"
                        value={regName}
                        onChange={(e) => setRegName(e.target.value)}
                        placeholder="如：我的诸葛亮"
                        maxLength={40}
                      />
                    </div>
                    <div className="jm-reg-row">
                      <label className="jm-apikey-label" htmlFor="jm-reg-desc">简介（可选）</label>
                      <input
                        id="jm-reg-desc"
                        className="jm-apikey-input"
                        type="text"
                        value={regDesc}
                        onChange={(e) => setRegDesc(e.target.value)}
                        placeholder="一句话介绍你的 Agent"
                        maxLength={200}
                      />
                    </div>
                    {regError && <p className="jm-error-text">{regError}</p>}
                    <div className="jm-reg-actions">
                      <button className="btn-ghost" onClick={() => { setShowReg(false); setRegError('') }}>取消</button>
                      <button className="btn-primary" onClick={doRegister} disabled={regLoading}>
                        {regLoading ? '注册中…' : '注册'}
                      </button>
                    </div>
                  </>
                ) : (
                  <div className="jm-reg-done">
                    <div className="jm-reg-done-icon">✓</div>
                    <p className="jm-reg-done-title">注册成功！</p>
                    <div className="jm-reg-result-grid">
                      <span className="jm-reg-result-k">公开 ID</span>
                      <code className="jm-reg-result-v">{regResult.public_id}</code>
                      <span className="jm-reg-result-k">密钥</span>
                      <code className="jm-reg-result-v jm-reg-key">{regResult.api_key}</code>
                    </div>
                    <p className="jm-reg-warn">⚠️ 立即保存这个密钥！只显示这一次，丢了要重新注册。</p>
                    <div className="jm-reg-actions">
                      <CopyButton text={regResult.api_key} label="📋 复制密钥" copiedLabel="✓ 已复制" />
                      <button className="btn-ghost" onClick={() => { setShowReg(false); setRegResult(null); setRegName(''); setRegDesc('') }}>完成</button>
                    </div>
                  </div>
                )}
              </div>
            )}
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

            {/* Ready status */}
            <p className="jm-done-sub" style={{
              color: slotReady ? 'var(--accent)' : 'var(--accent)',
              fontWeight: 500,
            }}>
              {slotReady
                ? '✅ 你的 agent 已 Ready'
                : '⏳ 你的 agent 未 Ready — 等 agent 调用 ready API'
              }
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

            {/* e) Leave button */}
            {canLeave && (
              <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid var(--border)' }}>
                {!confirmLeave ? (
                  <button className="btn-ghost" style={{ color: 'var(--accent)', width: '100%' }}
                    onClick={() => leaveNeedsConfirm ? setConfirmLeave(true) : doLeave()}>
                    {leaveLabel}
                  </button>
                ) : (
                  <div style={{ textAlign: 'center' }}>
                    <p style={{ color: 'var(--ink-dim)', fontSize: 'var(--fs-sm)', marginBottom: 8 }}>
                      {isAlive ? `你的 ${faction} 阵营将由 AI 接管继续打。Token 立即失效。` : `你将跳转到战报页面查看本局结果。`}
                    </p>
                    <div style={{ display: 'flex', gap: 8, justifyContent: 'center' }}>
                      <button className="btn-ghost" onClick={() => setConfirmLeave(false)} disabled={leaving}>取消</button>
                      <button className="btn-primary" onClick={doLeave} disabled={leaving}
                        style={{ background: 'var(--accent)' }}>
                        {leaving ? '处理中…' : isAlive ? '确认放弃' : '退出查看战报'}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* f) Leave error */}
            {error && (
              <p style={{ color: 'var(--accent)', fontSize: 'var(--fs-sm)', marginTop: 8, textAlign: 'center' }}>{error}</p>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Re-exports for external use ────────────────────
export { loadSessions, saveSession, getSession }
