import { useState, useEffect, useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'

export default function CommentaryPage() {
  const { id } = useParams()
  const [content, setContent] = useState(null)
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [countdown, setCountdown] = useState(0)
  const [state, setState] = useState(null)  // 'ready' | 'generating' | 'not_started' | 'failed' | 'unfinished'
  const [lastError, setLastError] = useState(null)

  const load = useCallback((isRetry) => {
    let cancelled = false
    if (!isRetry) {
      setLoading(true)
      setGenerating(false)
    }
    setState(null)
    setLastError(null)
    fetch(`/v1/games/${id}/commentary`)
      .then(async r => {
        const ct = r.headers.get('content-type') || ''

        // ── ready: plain text markdown ────────────────────
        if (r.status === 200 && ct.includes('text/plain')) {
          const text = await r.text()
          if (!cancelled) { setContent(text); setState('ready'); setLoading(false) }
          return
        }

        // ── generating (202) ──────────────────────────────
        if (r.status === 202) {
          try {
            const body = JSON.parse(await r.text())
            if (!cancelled) {
              setGenerating(true)
              setCountdown(body.retry_after_sec || 60)
              setState('generating')
              setLoading(false)
            }
          } catch {
            if (!cancelled) { setState('failed'); setLastError('响应格式异常'); setLoading(false) }
          }
          return
        }

        // ── 200 but JSON (not_started / failed / unfinished) ──
        if (r.status === 200 && ct.includes('application/json')) {
          const body = JSON.parse(await r.text())
          if (!cancelled) {
            if (body.error_code === 'COMMENTARY_NOT_STARTED') {
              setState('not_started')
            } else if (body.error_code === 'COMMENTARY_FAILED') {
              setState('failed')
              setLastError(body.last_error || '')
            } else {
              setState('not_started')  // fallback
            }
            setLoading(false)
          }
          return
        }

        // ── 425 (game not finished) ───────────────────────
        if (r.status === 425) {
          if (!cancelled) { setState('unfinished'); setLoading(false) }
          return
        }

        // ── unexpected ─────────────────────────────────────
        throw new Error(`HTTP ${r.status}`)
      })
      .catch(e => {
        if (!cancelled) { setState('failed'); setLastError(e.message); setLoading(false) }
      })
    return () => { cancelled = true }
  }, [id])

  useEffect(() => { load(false) }, [load])

  // Countdown tick
  useEffect(() => {
    if (!generating || countdown <= 0) return
    const timer = setTimeout(() => setCountdown(c => c - 1), 1000)
    return () => clearTimeout(timer)
  }, [generating, countdown])

  // Auto-refresh when countdown reaches 0
  useEffect(() => {
    if (generating && countdown === 0) load(true)
  }, [generating, countdown, load])

  const triggerGenerate = async () => {
    setLoading(true)
    setState(null)
    try {
      const r = await fetch(`/v1/games/${id}/commentary/generate`, { method: 'POST' })
      const body = await r.json().catch(() => ({}))
      if (r.ok) {
        setGenerating(true)
        setCountdown(body.retry_after_sec || 60)
        setState('generating')
        setLoading(false)
      } else if (r.status === 409) {
        // Already generating or ready — refresh
        load(false)
      } else {
        setState('failed')
        setLastError(body.detail || `HTTP ${r.status}`)
        setLoading(false)
      }
    } catch {
      setState('failed')
      setLastError('网络错误，请稍后重试')
      setLoading(false)
    }
  }

  if (loading) return <div className="bt-loading">加载中…</div>

  return (
    <div className="co-page">
      <div className="co-top">
        <Link to={`/battles/${id}`} className="bt-back">← 返回战报详情</Link>
        <span className="co-gameid">Game #{id}</span>
      </div>

      {/* ── ready: render markdown ──────────────────────── */}
      {state === 'ready' && content && (
        <div className="co-body"><ReactMarkdown>{content}</ReactMarkdown></div>
      )}
      {state === 'ready' && !content && (
        <div className="co-empty">暂无评书内容</div>
      )}

      {/* ── generating: countdown ─────────────────────────── */}
      {state === 'generating' && (
        <div className="co-generating">
          <p className="co-gen-title">评书正在生成中…</p>
          <p className="co-gen-hint">约 {countdown} 秒后自动刷新</p>
        </div>
      )}

      {/* ── not_started: trigger card ─────────────────────── */}
      {state === 'not_started' && (
        <div className="co-card">
          <p className="co-card-title">本对局尚无评书</p>
          <p className="co-card-desc">点击下方按钮，AI 评书人将为此战写下一段演义。</p>
          <button className="btn-primary co-gen-btn" onClick={triggerGenerate}>立即生成</button>
          <p className="co-card-footnote">生成约需 60-90 秒，期间消耗少量 API 配额</p>
        </div>
      )}

      {/* ── failed: retry card ────────────────────────────── */}
      {state === 'failed' && (
        <div className="co-card">
          <p className="co-card-title">评书生成失败</p>
          {lastError && <p className="co-card-desc">{lastError}</p>}
          <button className="btn-primary co-gen-btn" onClick={triggerGenerate}>重新生成</button>
        </div>
      )}

      {/* ── unfinished: game still in progress ────────────── */}
      {state === 'unfinished' && (
        <div className="co-card">
          <p className="co-card-title">对局尚未结束</p>
          <p className="co-card-desc">请等待对局结束后再查看评书。</p>
        </div>
      )}
    </div>
  )
}
