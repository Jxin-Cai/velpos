import { API_BASE } from '@shared/lib/constants'

const DEFAULT_TIMEOUT_MS = 30000

async function request(url, options = {}) {
  const fullUrl = `${API_BASE}${url}`
  const { timeoutMs = DEFAULT_TIMEOUT_MS, ...fetchOptions } = options
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const res = await fetch(fullUrl, { ...fetchOptions, signal: controller.signal })

    if (!res.ok) {
      // Try to extract business error message from response body
      let errorMsg = `HTTP error: ${res.status} ${res.statusText}`
      try {
        const body = await res.json()
        if (typeof body?.message === 'string' && body.message) {
          errorMsg = body.message
        } else if (typeof body?.detail === 'string' && body.detail) {
          // FastAPI's HTTPException serializes its business message as
          // {"detail": "..."}, rather than the ApiResponse shape.
          errorMsg = body.detail
        }
      } catch {
        // response body is not JSON, use default error message
      }
      throw new Error(errorMsg)
    }

    // Handle responses with no body (e.g. 204 No Content)
    const contentType = res.headers.get('content-type')
    if (res.status === 204 || !contentType || !contentType.includes('application/json')) {
      return null
    }

    const json = await res.json()

    if (json.code !== 0) {
      throw new Error(json.message || 'Unknown API error')
    }

    return json.data
  } catch (error) {
    if (controller.signal.aborted) {
      throw new Error(`Request timed out after ${Math.ceil(timeoutMs / 1000)} seconds`, { cause: error })
    }
    throw error
  } finally {
    clearTimeout(timeout)
  }
}

export function get(url, options = {}) {
  return request(url, { ...options, method: 'GET' })
}

export function post(url, body) {
  return request(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export function del(url) {
  return request(url, { method: 'DELETE' })
}

export function patch(url, body) {
  return request(url, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export function put(url, body) {
  return request(url, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}
