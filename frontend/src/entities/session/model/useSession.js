import { ref, computed, reactive } from 'vue'
import {
  markInteractiveMessageAnswered,
  preserveInteractiveAnswerState,
} from './interactiveMessageState'

// ── Per-session state map ──
// key: sessionId → { session, messages, status, error, queryHistory, runSteps, timelineEvents, queued, steeringQueued, _nextMsgId }
const _stateMap = reactive(new Map())

// ── Global state (not per-session) ──
const sessions = ref([])
const currentSessionId = ref(null)
const restoredPrompt = ref('')

// ── Internal helpers ──

function _ensureState(sessionId) {
  if (!sessionId) return null
  if (!_stateMap.has(sessionId)) {
    _stateMap.set(sessionId, {
      session: null,
      messages: [],
      messageWindow: {
        start_index: 0,
        end_index: 0,
        total_count: 0,
        has_more: false,
      },
      userMessageMarkers: [],
      status: 'disconnected',
      error: null,
      queryHistory: [],
      runSteps: [],
      timelineEvents: [],
      traceSpans: [],
      queued: false,
      steeringQueued: false,
      canceling: false,
      cancelledHint: false,
      _nextMsgId: 0,
    })
  }
  return _stateMap.get(sessionId)
}

function _assignIdFor(state, msg) {
  if (msg._id == null) {
    msg._id = msg._index ?? state._nextMsgId++
  }
  if (Number.isInteger(msg._index)) {
    state._nextMsgId = Math.max(state._nextMsgId, msg._index + 1)
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

const messageWindow = computed(() => {
  const state = _stateMap.get(currentSessionId.value)
  return state?.messageWindow || {
    start_index: 0,
    end_index: 0,
    total_count: 0,
    has_more: false,
  }
})

const userMessageMarkers = computed(() => {
  const state = _stateMap.get(currentSessionId.value)
  return state?.userMessageMarkers || []
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

const queued = computed(() => {
  const state = _stateMap.get(currentSessionId.value)
  return state ? state.queued : false
})

const canceling = computed(() => {
  const state = _stateMap.get(currentSessionId.value)
  return state ? state.canceling : false
})

const steeringQueued = computed(() => {
  const state = _stateMap.get(currentSessionId.value)
  return state ? state.steeringQueued : false
})

const cancelledHint = computed(() => {
  const state = _stateMap.get(currentSessionId.value)
  return state ? state.cancelledHint : false
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
  if (!msg.timestamp) msg.timestamp = Date.now()
  if (!Number.isInteger(msg._index)) {
    msg._index = state.messageWindow.end_index
  }
  _assignIdFor(state, msg)
  state.messages.push(msg)
  state.messageWindow.end_index = Math.max(state.messageWindow.end_index, msg._index + 1)
  state.messageWindow.total_count = Math.max(
    state.messageWindow.total_count,
    state.messageWindow.end_index,
  )
  state.messageWindow.has_more = state.messageWindow.start_index > 0
  if (msg.type === 'user') {
    const preview = String(msg.content?.text || '').replace(/\s+/g, ' ').trim()
    state.userMessageMarkers.push({
      index: msg._index,
      message_id: msg.content?.message_id || '',
      preview: preview || 'User message',
    })
  }
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

function removeMessageByClientIdFor(sessionId, messageId) {
  if (!messageId) return
  const state = _stateMap.get(sessionId)
  if (!state) return
  const index = state.messages.findIndex(message => (
    message.type === 'user' && message.content?.message_id === messageId
  ))
  if (index >= 0) {
    state.messages.splice(index, 1)
    const markerIndex = state.userMessageMarkers.findIndex(marker => (
      marker.message_id === messageId
    ))
    if (markerIndex >= 0) state.userMessageMarkers.splice(markerIndex, 1)
  }
}

function setMessagesFor(sessionId, msgs, sessionData) {
  const state = _ensureState(sessionId)
  if (!state) return
  // Skip replacement if messages haven't changed (cache hit on WS reconnect)
  if (state.messages.length === msgs.length && state.messages.length > 0) {
    const lastCached = state.messages[state.messages.length - 1]
    const lastNew = msgs[msgs.length - 1]
    if ((lastCached._id ?? lastCached.id) === (lastNew._id ?? lastNew.id)) {
      return
    }
  }
  const mergedMessages = preserveInteractiveAnswerState(state.messages, msgs)
  const windowData = sessionData?.message_window || {}
  const inferredStart = Number.isInteger(mergedMessages[0]?._index) ? mergedMessages[0]._index : 0
  const inferredEnd = inferredStart + mergedMessages.length
  state.messageWindow = {
    start_index: windowData.start_index ?? inferredStart,
    end_index: windowData.end_index ?? inferredEnd,
    total_count: windowData.total_count ?? inferredEnd,
    has_more: windowData.has_more ?? inferredStart > 0,
  }
  state.userMessageMarkers = Array.isArray(sessionData?.user_message_markers)
    ? sessionData.user_message_markers
    : mergedMessages
      .filter(message => message.type === 'user')
      .map(message => ({
        index: message._index ?? 0,
        message_id: message.content?.message_id || '',
        preview: String(message.content?.text || '').replace(/\s+/g, ' ').trim() || 'User message',
      }))
  state._nextMsgId = state.messageWindow.end_index
  state.messages.length = 0
  for (const message of mergedMessages) {
    state.messages.push(_assignIdFor(state, message))
  }
  _linkTraceRunsToUserMessages(state)
  // Rebuild queryHistory from existing result messages
  const resultMsgs = mergedMessages.filter(m => m.type === 'result' && m.content)
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

function markInteractiveAnsweredFor(sessionId, message) {
  const state = _stateMap.get(sessionId)
  if (!state) return false
  return markInteractiveMessageAnswered(state.messages, message)
}

function prependMessagesFor(sessionId, msgs, messageWindowData, markers = []) {
  const state = _ensureState(sessionId)
  if (!state || !Array.isArray(msgs) || msgs.length === 0) return
  const currentStart = state.messageWindow.start_index
  const pageEnd = messageWindowData?.end_index ?? currentStart
  if (pageEnd !== currentStart) return

  const incoming = msgs.map(message => _assignIdFor(state, message))
  state.messages.splice(0, 0, ...incoming)
  state.messageWindow = {
    start_index: messageWindowData?.start_index ?? incoming[0]?._index ?? 0,
    end_index: state.messageWindow.end_index,
    total_count: messageWindowData?.total_count ?? state.messageWindow.total_count,
    has_more: messageWindowData?.has_more ?? false,
  }
  if (Array.isArray(markers) && markers.length > 0) {
    state.userMessageMarkers = markers
  }
  _linkTraceRunsToUserMessages(state)
}

function getMessageWindowFor(sessionId) {
  return _stateMap.get(sessionId)?.messageWindow || null
}

function getUserMessageMarkersFor(sessionId) {
  return _stateMap.get(sessionId)?.userMessageMarkers || []
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

function setTimelineEventsFor(sessionId, events = []) {
  const state = _ensureState(sessionId)
  if (!state) return
  state.timelineEvents.length = 0
  state.timelineEvents.push(...events)
}

function upsertTimelineEventFor(sessionId, event) {
  const state = _ensureState(sessionId)
  if (!state || !event?.id) return
  const index = state.timelineEvents.findIndex(e => e.id === event.id)
  if (index >= 0) {
    state.timelineEvents[index] = { ...state.timelineEvents[index], ...event }
  } else {
    state.timelineEvents.push(event)
  }
  state.timelineEvents.sort((a, b) => {
    const runCmp = String(a.run_id || '').localeCompare(String(b.run_id || ''))
    if (runCmp !== 0) return runCmp
    return (a.seq || 0) - (b.seq || 0)
  })
}

function setTraceSpansFor(sessionId, spans = []) {
  const state = _ensureState(sessionId)
  if (!state) return
  state.traceSpans.length = 0
  state.traceSpans.push(...spans)
  _linkTraceRunsToUserMessages(state)
}

function upsertTraceSpanFor(sessionId, span) {
  const state = _ensureState(sessionId)
  if (!state || !span?.id) return
  const index = state.traceSpans.findIndex(s => s.id === span.id)
  if (index >= 0) {
    state.traceSpans[index] = { ...state.traceSpans[index], ...span }
  } else {
    state.traceSpans.push(span)
  }
  _linkTraceRunsToUserMessages(state)
}

function _linkTraceRunsToUserMessages(state) {
  const userMessages = state.messages.filter(message => message.type === 'user')
  if (!userMessages.length) return
  const roots = state.traceSpans
    .filter(span => span.span_type === 'run' && span.run_id)
    .sort((a, b) => String(a.started_time || '').localeCompare(String(b.started_time || '')))
  if (!roots.length) return

  // New traces carry an exact source message id.
  for (const root of roots) {
    const sourceMessageId = root.metadata?.source_message_id
    if (!sourceMessageId) continue
    const message = userMessages.find(item => item.content?.message_id === sourceMessageId)
    if (message && !message.content?.run_id) {
      message.content = { ...message.content, run_id: root.run_id }
    }
  }

  // Backfill traces created before source_message_id existed. Align from the
  // end so imported/untraced early conversation history is left untouched.
  const linkedRunIds = new Set(userMessages.map(item => item.content?.run_id).filter(Boolean))
  const unlinkedRoots = roots.filter(root => !linkedRunIds.has(root.run_id))
  const unlinkedMessages = userMessages.filter(message => !message.content?.run_id)
  const pairCount = Math.min(unlinkedRoots.length, unlinkedMessages.length)
  for (let offset = 1; offset <= pairCount; offset += 1) {
    const root = unlinkedRoots[unlinkedRoots.length - offset]
    const message = unlinkedMessages[unlinkedMessages.length - offset]
    message.content = { ...message.content, run_id: root.run_id }
  }
}

function mergeTraceSpansFor(sessionId, spans = []) {
  const state = _ensureState(sessionId)
  if (!state) return
  const byId = new Map(spans.map(span => [span.id, span]))
  for (const current of state.traceSpans) {
    const persisted = byId.get(current.id)
    if (!persisted || (persisted.status === 'running' && current.status !== 'running')) {
      byId.set(current.id, current)
    }
  }
  setTraceSpansFor(sessionId, [...byId.values()].sort((a, b) => (
    String(a.started_time || '').localeCompare(String(b.started_time || ''))
  )))
}

function linkUserMessageToRunFor(sessionId, messageId, runId) {
  const state = _ensureState(sessionId)
  if (!state || !runId) return
  let message = null
  if (messageId) {
    message = state.messages.find(item => (
      item.type === 'user' && item.content?.message_id === messageId
    ))
  }
  if (!message) {
    message = [...state.messages].reverse().find(item => (
      item.type === 'user' && !item.content?.run_id
    ))
  }
  if (message) {
    message.content = { ...message.content, message_id: messageId || message.content?.message_id, run_id: runId }
  }
}

function getTraceSpansFor(sessionId) {
  const state = _stateMap.get(sessionId)
  return state ? state.traceSpans : []
}

function setStatusFor(sessionId, s) {
  const state = _ensureState(sessionId)
  if (!state) return
  state.status = s
}

function setQueuedFor(sessionId, val) {
  const state = _ensureState(sessionId)
  if (!state) return
  state.queued = val
}

function setQueuedCommandFor(sessionId, command) {
  const state = _ensureState(sessionId)
  if (!state) return
  state.session = {
    ...state.session,
    recovery: {
      ...(state.session?.recovery || {}),
      queued_command: command || null,
    },
  }
  state.queued = Boolean(command)
}

function setSteeringQueuedFor(sessionId, val) {
  const state = _ensureState(sessionId)
  if (!state) return
  state.steeringQueued = Boolean(val)
}

function setErrorFor(sessionId, err) {
  const state = _ensureState(sessionId)
  if (!state) return
  state.error = err
}

function setCancelingFor(sessionId, val) {
  const state = _ensureState(sessionId)
  if (!state) return
  state.canceling = val
}

function getCancelingFor(sessionId) {
  const state = _stateMap.get(sessionId)
  return state ? state.canceling : false
}

const _cancelledHintTimers = new Map()

function showCancelledHintFor(sessionId) {
  const state = _ensureState(sessionId)
  if (!state) return
  const prev = _cancelledHintTimers.get(sessionId)
  if (prev) clearTimeout(prev)
  state.cancelledHint = true
  _cancelledHintTimers.set(sessionId, setTimeout(() => {
    state.cancelledHint = false
    _cancelledHintTimers.delete(sessionId)
  }, 2500))
}

function removeState(sessionId) {
  const timer = _cancelledHintTimers.get(sessionId)
  if (timer) {
    clearTimeout(timer)
    _cancelledHintTimers.delete(sessionId)
  }
  _stateMap.delete(sessionId)
}

function setRestoredPrompt(text) {
  restoredPrompt.value = text || ''
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

function setError(err) {
  setErrorFor(currentSessionId.value, err)
}

function setCanceling(val) {
  setCancelingFor(currentSessionId.value, val)
}

function setQueuedCommand(command) {
  setQueuedCommandFor(currentSessionId.value, command)
}

function setSteeringQueued(val) {
  setSteeringQueuedFor(currentSessionId.value, val)
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
    messageWindow,
    userMessageMarkers,
    status,
    error,
    queued,
    steeringQueued,
    canceling,
    cancelledHint,
    waitingForSlot,
    recovery,
    queryHistory,
    restoredPrompt,
    // Global state
    sessions,
    currentSessionId,
    // Current-session convenience APIs
    updateSession,
    addMessage,
    setMessages,
    setStatus,
    setError,
    setCanceling,
    setQueuedCommand,
    setSteeringQueued,
    // Session list management
    setSessions,
    setCurrentSessionId,
    addSession,
    removeSession,
    updateSessionInList,
    // Targeted APIs (write to specific session by ID)
    updateSessionFor,
    addMessageTo,
    removeMessageByClientIdFor,
    setMessagesFor,
    markInteractiveAnsweredFor,
    prependMessagesFor,
    getMessageWindowFor,
    getUserMessageMarkersFor,
    setRunStepsFor,
    upsertRunStepFor,
    setTimelineEventsFor,
    upsertTimelineEventFor,
    setTraceSpansFor,
    upsertTraceSpanFor,
    mergeTraceSpansFor,
    getTraceSpansFor,
    linkUserMessageToRunFor,
    setStatusFor,
    setQueuedFor,
    setQueuedCommandFor,
    setSteeringQueuedFor,
    setErrorFor,
    setCancelingFor,
    getCancelingFor,
    showCancelledHintFor,
    removeState,
    setRestoredPrompt,
  }
}
