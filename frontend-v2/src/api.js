const BASE = ''

// CSRF token — fetched from /v1/csrf on app startup, included in join calls
let csrfToken = null

export async function fetchCsrfToken() {
  try {
    const res = await fetch(`${BASE}/v1/csrf`)
    if (res.ok) {
      const data = await res.json()
      csrfToken = data.csrf_token
    }
  } catch {}
}

function csrfHeaders() {
  return csrfToken ? { 'X-CSRF-Token': csrfToken } : {}
}

class ApiError extends Error {
  constructor(message, { code, status, body } = {}) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
    this.body = body
  }
}

async function request(path, { method = 'GET', body, signal, headers = {}, credentials } = {}) {
  const opts = { method, signal, headers: { ...headers }, credentials }
  if (body != null) {
    opts.headers['Content-Type'] = 'application/json'
    opts.body = JSON.stringify(body)
  }

  let res
  try {
    res = await fetch(`${BASE}${path}`, opts)
  } catch (e) {
    if (e.name === 'AbortError') throw e
    throw new ApiError(`网络错误: ${e.message}`, { status: 0 })
  }

  // Prefer JSON; fall back to text for plaintext endpoints like /instruction
  const ct = res.headers.get('content-type') || ''
  const data = ct.includes('application/json') ? await res.json() : await res.text()

  if (!res.ok) {
    // On 401/410, auto-clear stale session so UI doesn't show phantom "已加入" banner
    if ((res.status === 401 || res.status === 410) && res.headers.get('content-type')?.includes('application/json')) {
      try {
        const sessions = JSON.parse(localStorage.getItem('arena_sessions') || '{}')
        if (Object.keys(sessions).length > 0) {
          localStorage.removeItem('arena_sessions')
          window.location.reload()
          return null
        }
      } catch {}
    }
    const detail = typeof data === 'string' ? data : data?.detail
    const errorCode = typeof data === 'object' ? data?.error_code : undefined
    throw new ApiError(detail || errorCode || `HTTP ${res.status}`, {
      code: errorCode,
      status: res.status,
      body: data,
    })
  }

  return data
}

export const api = {
  getLobbyStatus()       { return request('/v1/lobby/status') },
  joinLobby(faction) {
    const opts = { method: 'POST', body: { faction } }
    // CSRF: cookie is sent automatically via credentials, header via csrfHeaders
    const csrf = csrfHeaders()
    return request('/v1/lobby/join', {
      ...opts,
      headers: { ...csrf },
      credentials: 'include',
    })
  },
  assignAI(faction)      { return request('/v1/lobby/assign-ai', { method: 'POST', body: { faction } }) },
  releaseAI(faction)     { return request('/v1/lobby/release-ai', { method: 'POST', body: { faction } }) },
  ready(token)           { return request('/v1/lobby/ready',    { method: 'POST', body: { token } }) },
  getCurrentGame()       { return request('/current-game') },
}

export { ApiError, request }
