import { ref, reactive, computed, onScopeDispose, watch } from 'vue'
import { useSession } from '@entities/session'
import {
  fetchExecutionTree,
  fetchLlmRequestDetail,
  fetchLlmRequests,
  fetchLoopDetail,
} from '../api/traceApi'
import { traceRunVersion } from '../lib/traceHistory'
import { matchRequestsToLoops } from '../lib/llmRequestMatching'

const NodeStatus = Object.freeze({
  IDLE: 'idle',
  LOADING: 'loading',
  LOADED: 'loaded',
  ERROR: 'error',
})

const REFRESH_DEBOUNCE_MS = 1500
// A single step can hold hundreds of events, each carrying a full model context
// or tool payload. Render the first page immediately and let the reader pull the
// rest on demand instead of blocking on the whole step.
const DETAIL_PAGE_SIZE = 100

export function useExecutionTree() {
  const { currentSessionId, getTraceSpansFor } = useSession()

  const tree = ref(null)
  const loading = ref(false)
  const error = ref('')
  let refreshTimer = null
  let refreshPending = false
  let loadRequestId = 0
  let loadedContextKey = null

  const expandedTasks = reactive(new Set())
  const expandedLoops = reactive(new Set())
  const expandedSubagents = reactive(new Map())
  const inlineSubagents = reactive(new Map())

  const loopDetails = reactive(new Map())
  const loopLoadState = reactive(new Map())

  const llmRequests = ref([])
  const llmRequestDetails = reactive(new Map())

  const selectedRunId = ref(null)
  const selectedLoopId = ref(null)

  const tasks = computed(() => tree.value?.tasks || [])
  const agentId = computed(() => tree.value?.agent_id || '')
  const provenance = computed(() => tree.value?.provenance || null)
  const dependencies = computed(() => tree.value?.dependencies || [])
  const subagents = computed(() => tree.value?.subagents || [])

  function loopKey(loopId, agentSpanId = null) {
    return agentSpanId ? `${agentSpanId}:${loopId}` : loopId
  }

  function contextKey(sessionId, runId, agentSpanId = null) {
    return `${sessionId}:${runId}:${agentSpanId || 'main'}`
  }

  function resetViewerState() {
    selectedLoopId.value = null
    loopDetails.clear()
    loopLoadState.clear()
    llmRequestDetails.clear()
    expandedSubagents.clear()
    inlineSubagents.clear()
    expandedTasks.clear()
    expandedLoops.clear()
  }

  function reconcileViewerState(result) {
    const tasks = result?.tasks || []
    const taskIds = new Set(tasks.map(task => task.id))
    const loopIds = new Set(tasks.flatMap(task => (task.loops || []).map(loop => loop.id)))

    for (const taskId of expandedTasks) {
      if (!taskIds.has(taskId)) expandedTasks.delete(taskId)
    }
    for (const loopId of expandedLoops) {
      if (!loopIds.has(loopId)) expandedLoops.delete(loopId)
    }

    if (selectedLoopId.value && !loopIds.has(selectedLoopId.value)) {
      selectedLoopId.value = null
    }
  }

  async function loadTree(sessionId, runId, agentSpanId = null) {
    const requestId = ++loadRequestId
    const nextContextKey = contextKey(sessionId, runId, agentSpanId)
    const isSameContext = loadedContextKey === nextContextKey
    loading.value = true
    error.value = ''
    selectedRunId.value = runId
    try {
      const result = await fetchExecutionTree(sessionId, runId, agentSpanId)
      if (requestId !== loadRequestId) return

      if (isSameContext) {
        reconcileViewerState(result)
      } else {
        resetViewerState()
      }
      tree.value = result
      loadedContextKey = nextContextKey
      loadLlmRequests(sessionId, runId, requestId)
    } catch (err) {
      if (requestId !== loadRequestId) return
      error.value = isSameContext
        ? `Live refresh failed: ${err?.message || 'Unknown error'}`
        : (err?.message || 'Failed to load execution tree')
      if (!isSameContext) {
        tree.value = null
        loadedContextKey = null
      }
    } finally {
      if (requestId === loadRequestId) loading.value = false
    }
  }

  // Raw request bodies are optional telemetry: a run recorded with body logging
  // disabled is still a complete trace, so a failure here must not surface as a
  // tree error.
  async function loadLlmRequests(sessionId, runId, requestId) {
    try {
      const result = await fetchLlmRequests(sessionId, runId)
      if (requestId !== loadRequestId) return
      llmRequests.value = result?.requests || []
    } catch {
      if (requestId !== loadRequestId) return
      llmRequests.value = []
    }
  }

  const requestsByLoopId = computed(() => matchRequestsToLoops(
    tasks.value.flatMap(task => task.loops || []),
    llmRequests.value,
  ))

  function getLlmRequestForLoop(loopId) {
    return requestsByLoopId.value.get(loopId) || null
  }

  function getLlmRequestDetail(eventId) {
    return llmRequestDetails.get(eventId) || null
  }

  async function loadLlmRequestDetail(eventId) {
    if (!eventId || llmRequestDetails.get(eventId)?.loading) return
    const sessionId = currentSessionId.value
    if (!sessionId) return
    llmRequestDetails.set(eventId, { loading: true, detail: null, error: '' })
    try {
      const detail = await fetchLlmRequestDetail(sessionId, eventId)
      llmRequestDetails.set(eventId, { loading: false, detail, error: '' })
    } catch (err) {
      llmRequestDetails.set(eventId, {
        loading: false,
        detail: null,
        error: err?.message || 'Failed to load request',
      })
    }
  }

  async function loadLoopDetail(loopId, agentSpanId = null) {
    const key = loopKey(loopId, agentSpanId)
    if (loopLoadState.get(key) === NodeStatus.LOADING) return
    const sessionId = currentSessionId.value
    const runId = selectedRunId.value
    if (!sessionId || !runId) return

    loopLoadState.set(key, NodeStatus.LOADING)
    try {
      const page = await fetchLoopDetail(sessionId, runId, loopId, agentSpanId, 0, DETAIL_PAGE_SIZE)
      const items = page.items || []
      loopDetails.set(key, {
        items,
        next_cursor: advancedCursor(page.next_cursor, 0),
        total: Math.max(Number(page.total) || 0, items.length),
        loadingMore: false,
      })
      loopLoadState.set(key, NodeStatus.LOADED)
    } catch (err) {
      loopLoadState.set(key, NodeStatus.ERROR)
      loopDetails.set(key, { error: err?.message || 'Load failed' })
    }
  }

  // Treat a cursor that does not move forward as the end of the step. Otherwise a
  // backend that keeps returning the same cursor would let the reader append the
  // same page forever.
  function advancedCursor(nextCursor, requestedCursor) {
    return Number.isFinite(nextCursor) && nextCursor > requestedCursor ? nextCursor : null
  }

  async function loadMoreLoopEvents(loopId, agentSpanId = null) {
    const key = loopKey(loopId, agentSpanId)
    const current = loopDetails.get(key)
    if (!current?.items || current.next_cursor == null || current.loadingMore) return
    const sessionId = currentSessionId.value
    const runId = selectedRunId.value
    if (!sessionId || !runId) return

    const cursor = current.next_cursor
    loopDetails.set(key, { ...current, loadingMore: true, moreError: '' })
    try {
      const page = await fetchLoopDetail(sessionId, runId, loopId, agentSpanId, cursor, DETAIL_PAGE_SIZE)
      const items = [...current.items, ...(page.items || [])]
      loopDetails.set(key, {
        items,
        next_cursor: advancedCursor(page.next_cursor, cursor),
        total: Math.max(Number(page.total) || 0, items.length),
        loadingMore: false,
      })
    } catch (err) {
      loopDetails.set(key, {
        ...current,
        loadingMore: false,
        moreError: err?.message || 'Failed to load more events',
      })
    }
  }

  async function loadSubagentTree(spanId) {
    const sessionId = currentSessionId.value
    const runId = selectedRunId.value
    if (!sessionId || !runId) return

    expandedSubagents.set(spanId, { loading: true, tree: null, error: '' })
    try {
      const result = await fetchExecutionTree(sessionId, runId, spanId)
      expandedSubagents.set(spanId, { loading: false, tree: result, error: '' })
    } catch (err) {
      expandedSubagents.set(spanId, { loading: false, tree: null, error: err?.message || 'Load failed' })
    }
  }

  function expandTask(taskId) {
    expandedTasks.add(taskId)
  }

  function collapseTask(taskId) {
    expandedTasks.delete(taskId)
  }

  function toggleTask(taskId) {
    if (expandedTasks.has(taskId)) {
      expandedTasks.delete(taskId)
    } else {
      expandedTasks.add(taskId)
    }
  }

  function expandLoop(loopId) {
    expandedLoops.add(loopId)
    if (!loopDetails.has(loopId)) {
      loadLoopDetail(loopId)
    }
  }

  function collapseLoop(loopId) {
    expandedLoops.delete(loopId)
  }

  function toggleLoop(loopId) {
    if (expandedLoops.has(loopId)) {
      collapseLoop(loopId)
    } else {
      expandLoop(loopId)
    }
  }

  function expandSubagent(spanId) {
    if (!expandedSubagents.has(spanId)) {
      loadSubagentTree(spanId)
    }
  }

  function collapseSubagent(spanId) {
    expandedSubagents.delete(spanId)
  }

  function toggleSubagent(spanId) {
    if (expandedSubagents.has(spanId)) {
      collapseSubagent(spanId)
    } else {
      expandSubagent(spanId)
    }
  }

  async function loadInlineSubagentTree(spanId) {
    const sessionId = currentSessionId.value
    const runId = selectedRunId.value
    if (!sessionId || !runId) return

    inlineSubagents.set(spanId, { loading: true, tree: null, error: '' })
    try {
      const result = await fetchExecutionTree(sessionId, runId, spanId)
      inlineSubagents.set(spanId, { loading: false, tree: result, error: '' })
    } catch (err) {
      inlineSubagents.set(spanId, { loading: false, tree: null, error: err?.message || 'Load failed' })
    }
  }

  function toggleInlineSubagent(spanId) {
    if (inlineSubagents.has(spanId)) {
      inlineSubagents.delete(spanId)
    } else {
      loadInlineSubagentTree(spanId)
    }
  }

  function getInlineSubagentState(spanId) {
    return inlineSubagents.get(spanId) || null
  }

  function selectLoop(loopId) {
    if (selectedLoopId.value === loopId) {
      selectedLoopId.value = null
      return
    }
    selectedLoopId.value = loopId
    const state = getLoopLoadState(loopId)
    if (state === NodeStatus.IDLE || state === NodeStatus.ERROR) {
      loadLoopDetail(loopId)
    }
  }

  function isTaskExpanded(taskId) {
    return expandedTasks.has(taskId)
  }

  function isLoopExpanded(loopId) {
    return expandedLoops.has(loopId)
  }

  function getLoopDetail(loopId, agentSpanId = null) {
    return loopDetails.get(loopKey(loopId, agentSpanId)) || null
  }

  function getLoopLoadState(loopId, agentSpanId = null) {
    return loopLoadState.get(loopKey(loopId, agentSpanId)) || NodeStatus.IDLE
  }

  function getSubagentState(spanId) {
    return expandedSubagents.get(spanId) || null
  }

  function refreshSummary() {
    const sessionId = currentSessionId.value
    const runId = selectedRunId.value
    if (!sessionId || !runId) return
    loadTree(sessionId, runId)
  }

  function runPendingRefresh() {
    if (!refreshPending) return
    if (loading.value) {
      refreshTimer = setTimeout(runPendingRefresh, 250)
      return
    }
    refreshPending = false
    refreshSummary()
  }

  function debouncedRefresh() {
    if (!selectedRunId.value || !currentSessionId.value) return
    refreshPending = true
    clearTimeout(refreshTimer)
    refreshTimer = setTimeout(runPendingRefresh, REFRESH_DEBOUNCE_MS)
  }

  const traceSpans = computed(() => {
    const sid = currentSessionId.value
    return sid ? getTraceSpansFor(sid) : []
  })

  watch(
    () => traceRunVersion(traceSpans.value, selectedRunId.value),
    (version, previousVersion) => {
      if (previousVersion != null && version !== previousVersion && tree.value) {
        debouncedRefresh()
      }
    },
  )

  onScopeDispose(() => {
    clearTimeout(refreshTimer)
    refreshPending = false
    loadRequestId += 1
  })

  return {
    tree,
    loading,
    error,
    tasks,
    agentId,
    provenance,
    dependencies,
    subagents,
    selectedRunId,
    selectedLoopId,
    expandedTasks,
    expandedLoops,
    expandedSubagents,
    inlineSubagents,
    loadTree,
    loadLoopDetail,
    loadMoreLoopEvents,
    loadSubagentTree,
    loadInlineSubagentTree,
    expandTask,
    collapseTask,
    toggleTask,
    expandLoop,
    collapseLoop,
    toggleLoop,
    expandSubagent,
    collapseSubagent,
    toggleSubagent,
    toggleInlineSubagent,
    selectLoop,
    isTaskExpanded,
    isLoopExpanded,
    getLoopDetail,
    getLoopLoadState,
    getSubagentState,
    getInlineSubagentState,
    llmRequests,
    getLlmRequestForLoop,
    getLlmRequestDetail,
    loadLlmRequestDetail,
    refreshSummary,
    NodeStatus,
  }
}
