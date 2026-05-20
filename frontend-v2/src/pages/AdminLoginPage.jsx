import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

const TOKEN_KEY = 'arena_admin_token'

export function getAdminToken() { return localStorage.getItem(TOKEN_KEY) }
export function clearAdminToken() { localStorage.removeItem(TOKEN_KEY) }

export default function AdminLoginPage() {
  const [token, setToken] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  async function doLogin(e) {
    e.preventDefault()
    if (!token.trim()) return
    setLoading(true)
    setError('')
    try {
      // Verify token by hitting admin stats
      const resp = await fetch(`/api/admin/stats?token=${encodeURIComponent(token.trim())}`)
      if (!resp.ok) {
        const msg = resp.status === 401 ? 'Token 无效' : `HTTP ${resp.status}`
        setError(msg)
        setLoading(false)
        return
      }
      localStorage.setItem(TOKEN_KEY, token.trim())
      navigate('/admin')
    } catch { setError('网络错误'); setLoading(false) }
  }

  return (
    <div className="adm-login">
      <h1>管理后台</h1>
      <form onSubmit={doLogin}>
        <input
          type="password"
          value={token}
          onChange={e => setToken(e.target.value)}
          placeholder="Admin Token"
          className="adm-login-input"
          autoFocus
        />
        {error && <div className="adm-login-error">{error}</div>}
        <button type="submit" className="btn-primary" disabled={loading}>
          {loading ? '验证中…' : '登录'}
        </button>
      </form>
    </div>
  )
}
