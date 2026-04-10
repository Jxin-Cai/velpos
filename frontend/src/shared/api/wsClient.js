import {
  WS_CLOSE_NORMAL,
  WS_CLOSE_NOT_FOUND,
} from '@shared/lib/constants'

export function createWsConnection(sessionId) {
  let ws = null
  let reconnectTimer = null
  let eventHandler = null
  let reconnectAttempt = 0
  let destroyed = false

  const BACKOFF_BASE = 1000
  const BACKOFF_MAX = 30000
  const JITTER_MAX = 500

  function getReconnectDelay() {
    const delay = Math.min(BACKOFF_BASE * Math.pow(2, reconnectAttempt), BACKOFF_MAX)
    const jitter = Math.random() * JITTER_MAX * 2 - JITTER_MAX
    return Math.max(delay + jitter, 500)
  }

  function buildUrl() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${protocol}//${window.location.host}/ws/${sessionId}`
  }

  function connect() {
    ws = new WebSocket(buildUrl())

    ws.onopen = () => {
      reconnectAttempt = 0
    }

    ws.onmessage = (event) => {
      if (eventHandler) {
        try {
          const data = JSON.parse(event.data)
          eventHandler(data)
        } catch {
          // Ignore malformed messages
        }
      }
    }

    ws.onclose = (event) => {
      if (destroyed) return;
      if (event.code !== WS_CLOSE_NORMAL && event.code !== WS_CLOSE_NOT_FOUND) {
        const delay = getReconnectDelay()
        reconnectAttempt++
        reconnectTimer = setTimeout(() => {
          connect()
        }, delay)
      }
    }

    ws.onerror = () => {
      if (eventHandler) {
        eventHandler({ event: 'error', message: 'WebSocket connection failed' })
      }
    }
  }

  function send(data) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(data))
      return true
    }
    return false
  }

  function onEvent(handler) {
    eventHandler = handler
  }

  function close() {
    destroyed = true
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    if (ws) {
      ws.close(WS_CLOSE_NORMAL)
      ws = null
    }
  }

  function getReadyState() {
    return ws ? ws.readyState : WebSocket.CLOSED
  }

  connect()

  return { send, onEvent, close, getReadyState }
}
