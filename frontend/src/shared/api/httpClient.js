import { API_BASE } from '@shared/lib/constants'

async function request(url, options = {}) {
  const fullUrl = `${API_BASE}${url}`
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 30000)
  try {
    const res = await fetch(fullUrl, { ...options, signal: controller.signal })

    if (!res.ok) {
      // Try to extract business error message from response body
      let errorMsg = `HTTP error: ${res.status} ${res.statusText}`
      try {
        const body = await res.json()
        if (body && body.message) {
          errorMsg = body.message
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
  } finally {
    clearTimeout(timeout)
  }
}

export function get(url) {
  return request(url, { method: 'GET' })
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
