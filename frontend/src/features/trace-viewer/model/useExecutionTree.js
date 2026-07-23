import { ref, reactive, computed, onScopeDispose, watch } from 'vue'
import { useSession } from '@entities/session'
import { fetchExecutionTree, fetchLoopDetail } from '../api/traceApi'

const NodeStatus = Object.freeze({
  IDLE: 'idle',
  LOADING: 'loading',
  LOADED: 'loaded',
  ERROR: 'error',
})

const REFRESH_DEBOUNCE_MS = 1500

export function useExecutionTree() {
  const { currentSessionId, getTraceSpansFor } = useSession()

  const tree = ref(null)
  const loading = ref(false)
  const error = ref('')
  let refreshTimer = null
  let loadRequestId = 0
  let loadedContextKey = null

  const expandedTasks = reactive(new Set())
  const expandedLoops = reactive(new Set())
  const expandedSubagents = reactive(new Map())
  const inlineSubagents = reactive(new Map())

  const loopDetails = reactive(new Map())
  const loopLoadState = reactive(new Map())

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

  function resetViewerState(result) {
    selectedLoopId.value = null
    loopDetails.clear()
    loopLoadState.clear()
    expandedSubagents.clear()
    inlineSubagents.clear()
    expandedTasks.clear()
    expandedLoops.clear()
    for (const task of result?.tasks || []) {
      expandedTasks.add(task.id)
    }
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

    // Newly announced tasks default to expanded without reopening tasks that
    // the user explicitly collapsed before the live refresh.
    const previousTaskIds = new Set((tree.value?.tasks || []).map(task => task.id))
    for (const task of tasks) {
      if (!previousTaskIds.has(task.id)) expandedTasks.add(task.id)
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
        resetViewerState(result)
      }
      tree.value = result
      loadedContextKey = nextContextKey
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

  async function loadLoopDetail(loopId, agentSpanId = null) {
    const key = loopKey(loopId, agentSpanId)
    if (loopLoadState.get(key) === NodeStatus.LOADING) return
    const sessionId = currentSessionId.value
    const runId = selectedRunId.value
    if (!sessionId || !runId) return

    loopLoadState.set(key, NodeStatus.LOADING)
    try {
      const result = await fetchLoopDetail(sessionId, runId, loopId, agentSpanId)
      loopDetails.set(key, result)
      loopLoadState.set(key, NodeStatus.LOADED)
    } catch (err) {
      loopLoadState.set(key, NodeStatus.ERROR)
      loopDetails.set(key, { error: err?.message || 'Load failed' })
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

  function debouncedRefresh() {
    if (loading.value) return
    if (!selectedRunId.value || !currentSessionId.value) return
    clearTimeout(refreshTimer)
    refreshTimer = setTimeout(() => {
      if (!loading.value && selectedRunId.value && currentSessionId.value) {
        refreshSummary()
      }
    }, REFRESH_DEBOUNCE_MS)
  }

  const traceSpans = computed(() => {
    const sid = currentSessionId.value
    return sid ? getTraceSpansFor(sid) : []
  })

  watch(
    () => traceSpans.value.length,
    (newLen, oldLen) => {
      if (oldLen != null && newLen !== oldLen && tree.value) {
        debouncedRefresh()
      }
    },
  )

  onScopeDispose(() => {
    clearTimeout(refreshTimer)
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
    refreshSummary,
    NodeStatus,
  }
}
