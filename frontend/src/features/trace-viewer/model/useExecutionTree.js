import { ref, reactive, computed } from 'vue'
import { useSession } from '@entities/session'
import { fetchExecutionTree, fetchLoopDetail } from '../api/traceApi'

const NodeStatus = Object.freeze({
  IDLE: 'idle',
  LOADING: 'loading',
  LOADED: 'loaded',
  ERROR: 'error',
})

export function useExecutionTree() {
  const { currentSessionId } = useSession()

  const tree = ref(null)
  const loading = ref(false)
  const error = ref('')

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

  async function loadTree(sessionId, runId, agentSpanId = null) {
    loading.value = true
    error.value = ''
    selectedRunId.value = runId
    try {
      const result = await fetchExecutionTree(sessionId, runId, agentSpanId)
      tree.value = result
      expandedTasks.clear()
      expandedLoops.clear()
      if (result?.tasks?.length) {
        for (const task of result.tasks) {
          expandedTasks.add(task.id)
          for (const loop of task.loops || []) {
            // Surface agent calls immediately in the task chain so the
            // internal-process control is discoverable without extra clicks.
            if (loop.subagents?.length) expandedLoops.add(loop.id)
          }
        }
      }
    } catch (err) {
      error.value = err?.message || 'Failed to load execution tree'
      tree.value = null
    } finally {
      loading.value = false
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
    if (!expandedLoops.has(loopId)) {
      expandLoop(loopId)
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
