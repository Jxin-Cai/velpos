import { ref, computed, reactive } from 'vue'

// ── Per-session state map ──
// key: sessionId → { session, messages, status, error, queryHistory, runSteps, queued, _nextMsgId }
const _stateMap = reactive(new Map())

// ── Global state (not per-session) ──
const sessions = ref([])
const currentSessionId = ref(null)

// ── Internal helpers ──

function _ensureState(sessionId) {
  if (!sessionId) return null
  if (!_stateMap.has(sessionId)) {
    _stateMap.set(sessionId, {
      session: null,
      messages: [],
      status: 'disconnected',
      error: null,
      queryHistory: [],
      runSteps: [],
      queued: false,
      _nextMsgId: 0,
    })
  }
  return _stateMap.get(sessionId)
}

function _assignIdFor(state, msg) {
  if (msg._id == null) {
    msg._id = state._nextMsgId++
  }
  return msg
}

// ── Computed proxies (auto-route to current session) ──

const session = computed(() => {
  const state = _stateMap.get(currentSessionId.value)
  return state ? state.session : null
})

const messages = computed(() => {
  const state = _stateMap.get(currentSessionId.value)
  return state ? state.messages : []
})

const status = computed(() => {
  const state = _stateMap.get(currentSessionId.value)
  return state ? state.status : 'disconnected'
})

const error = computed(() => {
  const state = _stateMap.get(currentSessionId.value)
  return state ? state.error : null
})

const queryHistory = computed(() => {
  const state = _stateMap.get(currentSessionId.value)
  return state ? state.queryHistory : []
})

const runSteps = computed(() => {
  const state = _stateMap.get(currentSessionId.value)
  return state ? state.runSteps : []
})

const queued = computed(() => {
  const state = _stateMap.get(currentSessionId.value)
  return state ? state.queued : false
})

const waitingForSlot = computed(() => {
  const state = _stateMap.get(currentSessionId.value)
  return Boolean(state?.session?.waiting_for_slot)
})

const recovery = computed(() => {
  const state = _stateMap.get(currentSessionId.value)
  return state?.session?.recovery || null
})

// ── Targeted APIs (write to specific session by ID) ──

function updateSessionFor(sessionId, data) {
  const state = _ensureState(sessionId)
  if (!state) return
  state.session = { ...state.session, ...data }
}

function addMessageTo(sessionId, msg) {
  const state = _ensureState(sessionId)
  if (!state) return
  _assignIdFor(state, msg)
  state.messages.push(msg)
  // Collect result messages into queryHistory
  if (msg.type === 'result' && msg.content) {
    state.queryHistory.push({
      timestamp: Date.now(),
      duration_ms: msg.content.duration_ms || 0,
      num_turns: msg.content.num_turns || 0,
      is_error: msg.content.is_error || false,
      usage: msg.content.usage || { input_tokens: 0, output_tokens: 0 },
      total_cost_usd: msg.content.total_cost_usd || 0,
    })
  }
}

function setMessagesFor(sessionId, msgs, sessionData) {
  const state = _ensureState(sessionId)
  if (!state) return
  state._nextMsgId = msgs.length
  state.messages.length = 0
  state.messages.push(...msgs.map(m => _assignIdFor(state, m)))
  // Rebuild queryHistory from existing result messages
  const resultMsgs = msgs.filter(m => m.type === 'result' && m.content)
  if (resultMsgs.length > 0) {
    state.queryHistory.length = 0
    state.queryHistory.push(...resultMsgs.map(m => ({
      timestamp: Date.now(),
      duration_ms: m.content.duration_ms || 0,
      num_turns: m.content.num_turns || 0,
      is_error: m.content.is_error || false,
      usage: m.content.usage || { input_tokens: 0, output_tokens: 0 },
      total_cost_usd: m.content.total_cost_usd || 0,
    })))
  } else if (sessionData?.usage) {
    const u = sessionData.usage
    if ((u.input_tokens || 0) > 0 || (u.output_tokens || 0) > 0) {
      state.queryHistory.length = 0
      state.queryHistory.push({
        timestamp: Date.now(),
        duration_ms: 0,
        num_turns: 0,
        is_error: false,
        usage: { input_tokens: u.input_tokens || 0, output_tokens: u.output_tokens || 0 },
        total_cost_usd: 0,
      })
    } else {
      state.queryHistory.length = 0
    }
  } else {
    state.queryHistory.length = 0
  }
  console.debug(
    `[VP] setMessagesFor(${sessionId}): total=${msgs.length}, results=${resultMsgs.length}, queryHistory=${state.queryHistory.length}`
  )
}

function setRunStepsFor(sessionId, steps = []) {
  const state = _ensureState(sessionId)
  if (!state) return
  state.runSteps.length = 0
  state.runSteps.push(...steps)
}

function upsertRunStepFor(sessionId, step) {
  const state = _ensureState(sessionId)
  if (!state || !step?.id) return
  if (step.step_type === 'run' && !state.runSteps.some(s => s.run_id === step.run_id)) {
    state.runSteps.length = 0
  }
  const index = state.runSteps.findIndex(s => s.id === step.id)
  if (index >= 0) {
    state.runSteps[index] = { ...state.runSteps[index], ...step }
  } else {
    state.runSteps.push(step)
  }
  state.runSteps.sort((a, b) => String(a.started_time || '').localeCompare(String(b.started_time || '')))
}

function setStatusFor(sessionId, s) {
  const state = _ensureState(sessionId)
  if (!state) return
  state.status = s
  if (s === 'idle') {
    state.queued = false
  }
}

function setQueuedFor(sessionId, val) {
  const state = _ensureState(sessionId)
  if (!state) return
  state.queued = val
}

function setErrorFor(sessionId, err) {
  const state = _ensureState(sessionId)
  if (!state) return
  state.error = err
}

function ensureState(sessionId) {
  _ensureState(sessionId)
}

function removeState(sessionId) {
  _stateMap.delete(sessionId)
}

// ── Current-session convenience wrappers (backward-compatible) ──

function updateSession(data) {
  updateSessionFor(currentSessionId.value, data)
}

function addMessage(msg) {
  addMessageTo(currentSessionId.value, msg)
}

function setMessages(msgs, sessionData) {
  setMessagesFor(currentSessionId.value, msgs, sessionData)
}

function setStatus(s) {
  setStatusFor(currentSessionId.value, s)
}

function setQueued(val) {
  setQueuedFor(currentSessionId.value, val)
}

function setError(err) {
  setErrorFor(currentSessionId.value, err)
}

function reset() {
  const id = currentSessionId.value
  if (id) {
    _stateMap.delete(id)
  }
}

// ── Session list management (unchanged) ──

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

export function useSession() {
  return {
    // Computed proxies (read current session)
    session,
    messages,
    status,
    error,
    queued,
    waitingForSlot,
    recovery,
    queryHistory,
    runSteps,
    // Global state
    sessions,
    currentSessionId,
    // Current-session convenience APIs
    updateSession,
    addMessage,
    setMessages,
    setStatus,
    setQueued,
    setError,
    reset,
    // Session list management
    setSessions,
    setCurrentSessionId,
    addSession,
    removeSession,
    updateSessionInList,
    // Targeted APIs (write to specific session by ID)
    updateSessionFor,
    addMessageTo,
    setMessagesFor,
    setRunStepsFor,
    upsertRunStepFor,
    setStatusFor,
    setQueuedFor,
    setErrorFor,
    ensureState,
    removeState,
  }
}
