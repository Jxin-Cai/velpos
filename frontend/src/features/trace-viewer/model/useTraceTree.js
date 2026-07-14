import { computed, ref } from 'vue'
import { useSession } from '@entities/session'
import { fetchTraceRuns, fetchTraceTree } from '../api/traceApi'

export function useTraceTree() {
  const { currentSessionId, getTraceSpansFor, setTraceSpansFor } = useSession()
  const selectedRunId = ref(null)
  const loading = ref(false)
  const error = ref('')

  const traceSpans = computed(() => {
    return getTraceSpansFor(currentSessionId.value)
  })

  const traceTree = computed(() => {
    const spans = traceSpans.value
    if (!spans || spans.length === 0) return []

    const filtered = selectedRunId.value
      ? spans.filter(s => s.run_id === selectedRunId.value)
      : spans

    return buildTree(filtered)
  })

  const traceByRun = computed(() => {
    const spans = traceSpans.value
    if (!spans || spans.length === 0) return {}

    const grouped = {}
    for (const span of spans) {
      if (!grouped[span.run_id]) grouped[span.run_id] = []
      grouped[span.run_id].push(span)
    }
    return grouped
  })

  const runIds = computed(() => {
    return Object.keys(traceByRun.value).reverse()
  })

  const stats = computed(() => {
    const spans = selectedRunId.value
      ? (traceByRun.value[selectedRunId.value] || [])
      : traceSpans.value

    const toolCalls = spans.filter(s => s.span_type === 'tool_call')
    const totalDuration = Math.max(...spans.map(s => s.duration_ms || 0), 0)
    const failedCount = spans.filter(s => s.status === 'failed').length
    const cancelledCount = spans.filter(s => s.status === 'cancelled').length
    const runningCount = spans.filter(s => s.status === 'running').length
    const subagentCount = spans.filter(s => s.span_type === 'subagent').length

    return {
      spanCount: spans.length,
      toolCallCount: toolCalls.length,
      totalDurationMs: totalDuration,
      failedCount,
      cancelledCount,
      runningCount,
      subagentCount,
    }
  })

  async function loadTraceForRun(runId) {
    if (!currentSessionId.value) return
    loading.value = true
    try {
      error.value = ''
      const result = await fetchTraceTree(currentSessionId.value, runId)
      const otherRuns = getTraceSpansFor(currentSessionId.value)
        .filter(span => span.run_id !== runId)
      setTraceSpansFor(currentSessionId.value, [
        ...otherRuns,
        ...flattenTree(result?.tree || []),
      ])
      selectedRunId.value = runId
    } catch (err) {
      error.value = err?.message || 'Trace 加载失败'
    } finally {
      loading.value = false
    }
  }

  async function loadTraceHistory() {
    const sessionId = currentSessionId.value
    if (!sessionId) return
    loading.value = true
    error.value = ''
    try {
      const result = await fetchTraceRuns(sessionId)
      if (currentSessionId.value !== sessionId) return
      const persisted = result?.spans || []
      const current = getTraceSpansFor(sessionId)
      const merged = mergeTraceSpans(persisted, current)
      setTraceSpansFor(sessionId, merged)
      const mergedRunIds = [...new Set(merged.map(span => span.run_id).filter(Boolean))]
      const selectedStillExists = mergedRunIds.includes(selectedRunId.value)
      if (!selectedStillExists) {
        selectedRunId.value = mergedRunIds.length ? mergedRunIds[mergedRunIds.length - 1] : null
      }
    } catch (err) {
      error.value = err?.message || 'Trace 加载失败'
    } finally {
      loading.value = false
    }
  }

  function selectRun(runId) {
    selectedRunId.value = runId
  }

  return {
    currentSessionId,
    traceTree,
    traceByRun,
    runIds,
    selectedRunId,
    stats,
    loading,
    error,
    loadTraceForRun,
    loadTraceHistory,
    selectRun,
  }
}

function flattenTree(nodes) {
  const result = []
  for (const node of nodes) {
    const { children = [], ...span } = node
    result.push(span, ...flattenTree(children))
  }
  return result
}

function mergeTraceSpans(persisted, current) {
  const byId = new Map(persisted.map(span => [span.id, span]))
  for (const span of current) {
    const saved = byId.get(span.id)
    // Keep terminal live updates when the periodic DB flush is slightly behind.
    if (!saved || (saved.status === 'running' && span.status !== 'running')) {
      byId.set(span.id, span)
    }
  }
  return [...byId.values()].sort((a, b) => (
    (a.started_time || '').localeCompare(b.started_time || '')
  ))
}

function buildTree(spans) {
  const nodeMap = new Map()
  for (const s of spans) {
    nodeMap.set(s.id, { ...s, children: [] })
  }

  const roots = []
  for (const node of nodeMap.values()) {
    if (node.parent_span_id && nodeMap.has(node.parent_span_id)) {
      nodeMap.get(node.parent_span_id).children.push(node)
    } else {
      roots.push(node)
    }
  }

  const sortByTime = (a, b) => {
    const ta = a.started_time || ''
    const tb = b.started_time || ''
    return ta < tb ? -1 : ta > tb ? 1 : 0
  }

  for (const node of nodeMap.values()) {
    node.children.sort(sortByTime)
  }
  roots.sort(sortByTime)

  return roots
}
