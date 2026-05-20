import { useState, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'

export default function MarkdownPage({ url, title, eyebrow }) {
  const [content, setContent] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    fetch(url)
      .then(async r => {
        const text = await r.text()
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        if (!cancelled) { setContent(text); setError(null) }
      })
      .catch(e => { if (!cancelled) setError(e.message) })
    return () => { cancelled = true }
  }, [url])

  return (
    <div className="md-page">
      {eyebrow && <div className="md-eyebrow">{eyebrow}</div>}
      {title && <h1 className="md-title">{title}</h1>}

      {error && <div className="md-error">加载失败: {error}</div>}

      {content ? (
        <div className="md-body">
          <ReactMarkdown>{content}</ReactMarkdown>
        </div>
      ) : !error ? (
        <div className="md-loading">加载中…</div>
      ) : null}
    </div>
  )
}
