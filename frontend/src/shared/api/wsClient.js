import {
  WS_CLOSE_AUTH_REQUIRED,
  WS_CLOSE_NORMAL,
  WS_CLOSE_NOT_FOUND,
} from '@shared/lib/constants'
import { AUTH_REQUIRED_EVENT } from '@shared/api/httpClient'

function _getWsTokenParam() {
  const token = localStorage.getItem('velpos_auth_token')
  return token ? `?token=${encodeURIComponent(token)}` : ''
}

/**
 * Internal base factory — encapsulates all shared WebSocket lifecycle concerns:
 * URL construction, exponential-backoff reconnect, destroyed guard, reconnectTimer
 * management, onEvent setter, and close/destroy logic.
 *
 * Callers supply only their differential behaviour via option hooks:
 *   onOpen(ws, wasReconnect)  — called after successful open, before attempt reset
 *   onMessage(event, getEventHandler)  — overrides default JSON-parse + dispatch
 *   onClose(event, getEventHandler)    — called before reconnect scheduling
 *   onError(event, getEventHandler)    — ws.onerror override (omitted if null)
 *   useJitter  — adds ±500ms jitter to backoff delay (default: false)
 *   backoffMax — ms cap for reconnect delay (default: 30000)
 *   skipReconnectCode — ws close code that suppresses reconnect (default: null)
 */
function _createBaseConnection(path, {
  onOpen = null,
  onMessage = null,
  onClose = null,
  onError = null,
  useJitter = false,
  backoffMax = 30000,
  skipReconnectCode = null,
} = {}) {
  let ws = null
  let reconnectTimer = null
  let eventHandler = null
  let reconnectAttempt = 0
  let destroyed = false

  function buildUrl() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${protocol}//${window.location.host}${path}${_getWsTokenParam()}`
  }

  function getDelay() {
    const base = Math.min(1000 * Math.pow(2, reconnectAttempt), backoffMax)
    if (!useJitter) return base
    const jitter = Math.random() * 1000 - 500  // ±500 ms
    return Math.max(base + jitter, 500)
  }

  function connect() {
    ws = new WebSocket(buildUrl())
    ws.onopen = () => {
      const wasReconnect = reconnectAttempt > 0
      reconnectAttempt = 0
      onOpen?.(ws, wasReconnect)
    }
    ws.onmessage = onMessage
      ? (event) => onMessage(event, () => eventHandler)
      : (event) => {
          if (!eventHandler) return
          try { eventHandler(JSON.parse(event.data)) } catch { /* ignore malformed */ }
        }
    ws.onclose = (event) => {
      onClose?.(event, () => eventHandler)
      if (destroyed) return
      if (event.code === WS_CLOSE_AUTH_REQUIRED) {
        window.dispatchEvent(new CustomEvent(AUTH_REQUIRED_EVENT))
        return
      }
      if (skipReconnectCode != null && event.code === skipReconnectCode) return
      reconnectAttempt++
      reconnectTimer = setTimeout(connect, getDelay())
    }
    if (onError) ws.onerror = (event) => onError(event, () => eventHandler)
  }

  function handleVisibilityChange() {
    if (destroyed || document.hidden) return
    if (!ws || ws.readyState === WebSocket.CLOSED || ws.readyState === WebSocket.CLOSING) {
      if (reconnectTimer) clearTimeout(reconnectTimer)
      reconnectAttempt = 0
      connect()
    }
  }

  document.addEventListener('visibilitychange', handleVisibilityChange)

  function onEvent(handler) { eventHandler = handler }

  function close() {
    destroyed = true
    document.removeEventListener('visibilitychange', handleVisibilityChange)
    if (reconnectTimer) clearTimeout(reconnectTimer)
    if (ws) ws.close(WS_CLOSE_NORMAL)
  }

  connect()
  return { ws: () => ws, onEvent, close }
}

export function createGlobalEventConnection() {
  let reconnectHandler = null

  const base = _createBaseConnection('/ws/events', {
    onOpen: (_ws, wasReconnect) => {
      if (wasReconnect && reconnectHandler) reconnectHandler()
    },
    // onMessage: use base default (JSON.parse + eventHandler, ignore malformed)
    // useJitter: false (pure exponential backoff, no jitter — intentional for global events)
    // backoffMax: 30000 (default)
  })

  function onReconnect(handler) { reconnectHandler = handler }

  return { onEvent: base.onEvent, onReconnect, close: base.close }
}

export function createWsConnection(sessionId) {
  let heartbeatTimer = null
  let lastServerEventAt = 0
  const pendingPrompts = new Map()

  const HEARTBEAT_INTERVAL = 25000
  const HEARTBEAT_TIMEOUT = 75000

  const base = _createBaseConnection(`/ws/${sessionId}`, {
    useJitter: true,
    skipReconnectCode: WS_CLOSE_NOT_FOUND,

    onOpen: (ws) => {
      lastServerEventAt = Date.now()
      for (const payload of pendingPrompts.values()) {
        ws.send(JSON.stringify(payload))
      }
      heartbeatTimer = setInterval(() => {
        if (ws?.readyState === WebSocket.OPEN) {
          const elapsed = Date.now() - lastServerEventAt
          if (elapsed > HEARTBEAT_TIMEOUT) {
            if (elapsed > HEARTBEAT_TIMEOUT + HEARTBEAT_INTERVAL) {
              // Two full intervals without any server event — connection is dead
              ws.close()
              return
            }
            // First timeout detection — send ping to probe before closing
            ws.send(JSON.stringify({ action: 'ping', timestamp: Date.now() }))
            return
          }
          ws.send(JSON.stringify({ action: 'ping', timestamp: Date.now() }))
        }
      }, HEARTBEAT_INTERVAL)
    },

    onMessage: (event, getEventHandler) => {
      const handler = getEventHandler()
      if (!handler) return
      try {
        const data = JSON.parse(event.data)
        lastServerEventAt = Date.now()
        if (
          data.message_id
          && ['prompt_started', 'message_queued', 'status_change', 'error'].includes(data.event)
        ) {
          pendingPrompts.delete(data.message_id)
        }
        handler(data)
      } catch (error) {
        handler({ event: 'protocol_error', message: `Malformed WebSocket event: ${error.message}` })
      }
    },

    onClose: (event, getEventHandler) => {
      if (heartbeatTimer) {
        clearInterval(heartbeatTimer)
        heartbeatTimer = null
      }
      // Notify handler that the connection dropped — lets UI clear stale status
      const handler = getEventHandler()
      if (handler) handler({ event: 'ws_disconnected', code: event.code })
    },

    onError: (_event, getEventHandler) => {
      const handler = getEventHandler()
      if (handler) handler({ event: 'error', message: 'WebSocket connection failed' })
    },
  })

  function send(data) {
    const isPrompt = data?.action === 'send_prompt' && data.message_id
    if (isPrompt) pendingPrompts.set(data.message_id, data)
    const ws = base.ws()
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(data))
      return true
    }
    return Boolean(isPrompt)
  }

  function close() {
    if (heartbeatTimer) {
      clearInterval(heartbeatTimer)
      heartbeatTimer = null
    }
    pendingPrompts.clear()
    base.close()
  }

  function getReadyState() {
    const ws = base.ws()
    return ws ? ws.readyState : WebSocket.CLOSED
  }

  return { send, onEvent: base.onEvent, close, getReadyState }
}
