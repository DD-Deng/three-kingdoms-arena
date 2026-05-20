import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'

export default function CommentaryPage() {
  const { id } = useParams()
  const [content, setContent] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    fetch(`/v1/games/${id}/commentary`)
      .then(async r => {
        if (!r.ok) throw new Error(r.status === 425 ? '对局仍在进行中' : `HTTP ${r.status}`)
        const text = await r.text()
        if (!cancelled) { setContent(text); setLoading(false) }
      })
      .catch(e => { if (!cancelled) { setError(e.message); setLoading(false) } })
    return () => { cancelled = true }
  }, [id])

  if (loading) return <div className="bt-loading">加载中…</div>
  if (error) return <div className="bt-error">加载失败: {error}</div>

  return (
    <div className="co-page">
      <div className="co-top">
        <Link to={`/battles/${id}`} className="bt-back">← 返回战报详情</Link>
        <span className="co-gameid">Game #{id}</span>
      </div>

      {content ? (
        <div className="co-body">
          <ReactMarkdown>{content}</ReactMarkdown>
        </div>
      ) : (
        <div className="co-empty">暂无评书内容</div>
      )}
    </div>
  )
}
