const BASE = ''

class ApiError extends Error {
  constructor(message, { code, status, body } = {}) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
    this.body = body
  }
}

async function request(path, { method = 'GET', body, signal } = {}) {
  const opts = { method, signal }
  if (body != null) {
    opts.headers = { 'Content-Type': 'application/json' }
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
  joinLobby(faction)     { return request('/v1/lobby/join',     { method: 'POST', body: { faction } }) },
  assignAI(faction)      { return request('/v1/lobby/assign-ai', { method: 'POST', body: { faction } }) },
  releaseAI(faction)     { return request('/v1/lobby/release-ai', { method: 'POST', body: { faction } }) },
  ready(token)           { return request('/v1/lobby/ready',    { method: 'POST', body: { token } }) },
  getCurrentGame()       { return request('/current-game') },
}

export { ApiError, request }
