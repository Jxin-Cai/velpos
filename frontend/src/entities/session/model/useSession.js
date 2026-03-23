import { ref } from 'vue'

// Module-level singleton state
const session = ref(null)
const messages = ref([])
const status = ref('disconnected')
const error = ref(null)
const sessions = ref([])
const currentSessionId = ref(null)
const queryHistory = ref([])

// Stable message ID counter — survives across setMessages/addMessage calls
let _nextMsgId = 0

function _assignId(msg) {
  if (msg._id == null) {
    msg._id = _nextMsgId++
  }
  return msg
}

export function useSession() {
  function updateSession(data) {
    session.value = { ...session.value, ...data }
  }

  function addMessage(msg) {
    _assignId(msg)
    messages.value.push(msg)
    // Collect result messages into queryHistory
    if (msg.type === 'result' && msg.content) {
      queryHistory.value.push({
        timestamp: Date.now(),
        duration_ms: msg.content.duration_ms || 0,
        num_turns: msg.content.num_turns || 0,
        is_error: msg.content.is_error || false,
        usage: msg.content.usage || { input_tokens: 0, output_tokens: 0 },
        total_cost_usd: msg.content.total_cost_usd || 0,
      })
    }
  }

  function setMessages(msgs, sessionData) {
    _nextMsgId = msgs.length
    messages.value = msgs.map(m => _assignId(m))
    // Rebuild queryHistory from existing result messages
    const resultMsgs = msgs.filter(m => m.type === 'result' && m.content)
    if (resultMsgs.length > 0) {
      queryHistory.value = resultMsgs.map(m => ({
        timestamp: Date.now(),
        duration_ms: m.content.duration_ms || 0,
        num_turns: m.content.num_turns || 0,
        is_error: m.content.is_error || false,
        usage: m.content.usage || { input_tokens: 0, output_tokens: 0 },
        total_cost_usd: m.content.total_cost_usd || 0,
      }))
    } else if (sessionData?.usage) {
      const u = sessionData.usage
      if ((u.input_tokens || 0) > 0 || (u.output_tokens || 0) > 0) {
        queryHistory.value = [{
          timestamp: Date.now(),
          duration_ms: 0,
          num_turns: 0,
          is_error: false,
          usage: { input_tokens: u.input_tokens || 0, output_tokens: u.output_tokens || 0 },
          total_cost_usd: 0,
        }]
      } else {
        queryHistory.value = []
      }
    } else {
      queryHistory.value = []
    }
    console.debug(
      `[VP] setMessages: total=${msgs.length}, results=${resultMsgs.length}, queryHistory=${queryHistory.value.length}`
    )
  }

  function setStatus(s) {
    status.value = s
  }

  function setError(err) {
    error.value = err
  }

  function reset() {
    session.value = null
    messages.value = []
    status.value = 'disconnected'
    error.value = null
    queryHistory.value = []
  }

  function setSessions(list) {
    sessions.value = list
  }

  function setCurrentSessionId(id) {
    currentSessionId.value = id
  }

  function addSession(newSession) {
    sessions.value.unshift(newSession)
  }

  function removeSession(id) {
    sessions.value = sessions.value.filter(s => s.session_id !== id)
  }

  function updateSessionInList(id, data) {
    const index = sessions.value.findIndex(s => s.session_id === id)
    if (index !== -1) {
      sessions.value[index] = { ...sessions.value[index], ...data }
    }
  }

  return {
    session,
    messages,
    status,
    error,
    sessions,
    currentSessionId,
    queryHistory,
    updateSession,
    addMessage,
    setMessages,
    setStatus,
    setError,
    reset,
    setSessions,
    setCurrentSessionId,
    addSession,
    removeSession,
    updateSessionInList,
  }
}
