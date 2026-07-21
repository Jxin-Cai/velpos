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
    const abandonedCount = spans.filter(s => s.status === 'abandoned').length
    const subagentCount = spans.filter(s => s.span_type === 'subagent').length
    const turnCount = spans.filter(s => (
      s.span_type === 'llm_turn'
      && Boolean(s.input_preview || s.output_preview || s.metadata?.thinking_preview || s.metadata?.tool_names?.length)
    )).length

    return {
      spanCount: spans.length,
      toolCallCount: toolCalls.length,
      totalDurationMs: totalDuration,
      failedCount,
      cancelledCount,
      runningCount,
      abandonedCount,
      subagentCount,
      turnCount,
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

  repairToolParents(nodeMap)

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

  for (const root of roots) {
    if (root.span_type === 'run') ensureMainAgentGroup(root)
    pruneEmptyTurns(root)
  }
  annotateTree(roots)

  return roots
}

function pruneEmptyTurns(node) {
  for (const child of node.children || []) pruneEmptyTurns(child)
  node.children = (node.children || []).filter(child => {
    if (child.span_type !== 'llm_turn') return true
    return Boolean(
      child.children?.length
      || child.input_preview
      || child.output_preview
      || child.metadata?.thinking_preview
      || meaningfulMetadataKeys(child.metadata).length,
    )
  })
}

function meaningfulMetadataKeys(metadata = {}) {
  const internalKeys = new Set([
    'role', 'inferred', 'tool_names', 'tool_use_ids', 'parent_tool_use_id', 'source',
  ])
  return Object.keys(metadata).filter(key => !internalKeys.has(key))
}

function repairToolParents(nodeMap) {
  const turns = [...nodeMap.values()]
    .filter(node => node.span_type === 'llm_turn')
    .sort((a, b) => String(a.started_time || '').localeCompare(String(b.started_time || '')))
  const tools = [...nodeMap.values()].filter(node => node.span_type === 'tool_call')
  const claimed = new Set(tools.filter(tool => nodeMap.get(tool.parent_span_id)?.span_type === 'llm_turn').map(tool => tool.id))

  for (const turn of turns) {
    const ids = Array.isArray(turn.metadata?.tool_use_ids) ? turn.metadata.tool_use_ids.filter(Boolean) : []
    for (const id of ids) {
      const tool = tools.find(candidate => candidate.tool_use_id === id)
      if (!tool) continue
      tool.parent_span_id = turn.id
      claimed.add(tool.id)
    }

    // Older traces only stored tool names. Match each announced tool to the
    // nearest unclaimed hook span, which repairs the historic run-level rows.
    const names = Array.isArray(turn.metadata?.tool_names) ? turn.metadata.tool_names : []
    for (const name of names) {
      const candidates = tools.filter(tool => (
        !claimed.has(tool.id)
        && tool.name === name
        && tool.run_id === turn.run_id
        && tool.parent_span_id === turn.parent_span_id
        && (!turn.agent_id || !tool.agent_id || turn.agent_id === tool.agent_id)
      ))
      if (!candidates.length) continue
      const turnTime = Date.parse(turn.started_time || '') || 0
      candidates.sort((a, b) => (
        Math.abs((Date.parse(a.started_time || '') || 0) - turnTime)
        - Math.abs((Date.parse(b.started_time || '') || 0) - turnTime)
      ))
      candidates[0].parent_span_id = turn.id
      claimed.add(candidates[0].id)
    }
  }
}

function ensureMainAgentGroup(run) {
  let mainAgent = run.children.find(node => (
    node.span_type === 'agent' || node.metadata?.role === 'main'
  ))
  const directWork = run.children.filter(node => (
    node.span_type === 'llm_turn' || node.span_type === 'tool_call'
  ))
  if (!mainAgent && directWork.length) {
    mainAgent = {
      id: `virtual-main-agent-${run.id}`,
      run_id: run.run_id,
      parent_span_id: run.id,
      span_type: 'agent',
      name: 'Main agent',
      status: run.status,
      duration_ms: run.duration_ms,
      started_time: run.started_time,
      ended_time: run.ended_time,
      metadata: { role: 'main', inferred: true },
      children: [],
      virtual: true,
    }
    run.children.unshift(mainAgent)
  }
  if (!mainAgent) return
  mainAgent.children.push(...directWork)
  run.children = run.children.filter(node => !directWork.includes(node))
  mainAgent.children.sort((a, b) => String(a.started_time || '').localeCompare(String(b.started_time || '')))
}

function annotateTree(roots) {
  const visit = (node, agentState = { turn: 0 }) => {
    const nextAgentState = (node.span_type === 'agent' || node.span_type === 'subagent')
      ? { turn: 0 }
      : agentState
    if (node.span_type === 'llm_turn') {
      nextAgentState.turn += 1
      node.turn_index = nextAgentState.turn
    }
    for (const child of node.children || []) visit(child, nextAgentState)
    node.tool_count = (node.children || []).reduce((count, child) => (
      count + (child.span_type === 'tool_call' ? 1 : 0) + (child.tool_count || 0)
    ), 0)
  }
  for (const root of roots) visit(root)
}
