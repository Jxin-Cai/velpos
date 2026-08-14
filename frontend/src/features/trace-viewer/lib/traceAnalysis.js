export const TracePresentation = Object.freeze({
  FLOW: 'flow',
  DURATION: 'duration',
  TOKENS: 'tokens',
})

const CONTAINER_SPAN_TYPES = new Set(['run', 'agent'])
const SPAN_DETAIL_LEVEL = Object.freeze({
  run: 0,
  agent: 1,
  subagent: 2,
  llm_turn: 3,
  otel_span: 3,
  tool_call: 4,
  tool_execution: 5,
  permission_wait: 6,
  hook: 7,
})

export function flattenTraceNodes(nodes = []) {
  const result = []
  for (const node of nodes) {
    result.push(node)
    if (node.children?.length) result.push(...flattenTraceNodes(node.children))
  }
  return result
}

export function spanTokenCount(span) {
  const metadata = span?.metadata || {}
  return Math.max(Number(metadata.input_tokens) || 0, 0)
    + Math.max(Number(metadata.output_tokens) || 0, 0)
}

export function subagentInvocationKey(span) {
  if (!span) return null
  const metadata = span.metadata || {}
  const isDedicatedSpan = span.span_type === 'subagent'
  const isAgentTool = span.span_type === 'tool_call' && (
    String(span.name || '').toLowerCase() === 'agent'
    || Boolean(metadata.subagent_type || metadata.agent_type)
  )
  if (!isDedicatedSpan && !isAgentTool) return null
  return span.tool_use_id
    || metadata.tool_use_id
    || metadata.parent_tool_use_id
    || span.id
}

export function isSubagentTraceSpan(span) {
  return subagentInvocationKey(span) != null
}

export function countSubagentInvocations(spans = []) {
  return new Set(spans.map(subagentInvocationKey).filter(Boolean)).size
}

export function subagentDisplayName(value) {
  const metadata = value?.metadata || {}
  const explicitName = value?.subagent
    || metadata.subagent_type
    || metadata.agent_type
    || value?.agent_id
  if (explicitName) return explicitName
  const spanName = String(value?.name || '').trim()
  return spanName && spanName.toLowerCase() !== 'agent' ? spanName : 'Subagent'
}

export function buildSubagentRoster(spans = [], executionSubagents = []) {
  const roster = new Map()
  for (const span of spans) {
    const key = subagentInvocationKey(span)
    if (!key) continue
    roster.set(key, {
      key,
      tool_use_id: span.tool_use_id || span.metadata?.tool_use_id || key,
      span_id: span.id || null,
      subagent: subagentDisplayName(span),
      status: span.status || 'recorded',
      duration_ms: Math.max(Number(span.duration_ms) || 0, 0),
      is_expandable: Boolean(span.id),
    })
  }
  for (const subagent of executionSubagents || []) {
    const key = subagent.tool_use_id || subagent.span_id
    if (!key) continue
    const existing = roster.get(key) || {}
    roster.set(key, {
      ...existing,
      ...subagent,
      key,
      subagent: subagentDisplayName(subagent) === 'Subagent'
        ? (existing.subagent || 'Subagent')
        : subagentDisplayName(subagent),
      span_id: subagent.span_id || existing.span_id || null,
      status: subagent.status || existing.status || 'recorded',
      duration_ms: Math.max(Number(subagent.duration_ms ?? existing.duration_ms) || 0, 0),
      is_expandable: subagent.is_expandable !== false && Boolean(subagent.span_id || existing.span_id),
    })
  }
  return [...roster.values()]
}

export function buildTraceAnalysis(nodes = []) {
  const spans = flattenTraceNodes(nodes)
  const actionable = spans.filter(span => !CONTAINER_SPAN_TYPES.has(span.span_type))
  const durations = actionable
    .map(span => Math.max(Number(span.duration_ms) || 0, 0))
    .filter(Boolean)
    .sort((a, b) => a - b)
  const totalTokens = actionable.reduce((total, span) => total + spanTokenCount(span), 0)
  const thresholds = {
    p50: percentileThreshold(durations, 0.5),
    p75: percentileThreshold(durations, 0.75),
    p90: percentileThreshold(durations, 0.9),
  }

  const rows = actionable.map((span) => {
    const durationMs = Math.max(Number(span.duration_ms) || 0, 0)
    const selfDurationMs = spanSelfDuration(span, actionable)
    const tokens = spanTokenCount(span)
    return {
      span,
      durationMs,
      selfDurationMs,
      tokens,
      tokenShare: totalTokens > 0 ? tokens / totalTokens : 0,
      durationBand: durationBand(durationMs, thresholds),
    }
  })

  return { rows, thresholds, totalTokens }
}

export function rankTraceRows(rows, presentation) {
  const metric = presentation === TracePresentation.TOKENS ? 'tokens' : 'selfDurationMs'
  return rows
    .filter(row => row[metric] > 0)
    .slice()
    .sort((a, b) => (
      b[metric] - a[metric]
      || b.durationMs - a.durationMs
      || String(a.span.started_time || '').localeCompare(String(b.span.started_time || ''))
    ))
}

export function spanSelfDuration(span, peerSpans = []) {
  const durationMs = Math.max(Number(span?.duration_ms) || 0, 0)
  if (!durationMs) return durationMs
  const startMs = Date.parse(span.started_time || '')
  if (!Number.isFinite(startMs)) return durationMs
  const endMs = startMs + durationMs
  const explicitChildren = new Set((span.children || []).map(child => child.id))
  const detailLevel = SPAN_DETAIL_LEVEL[span.span_type] ?? 3
  const candidates = [...(span.children || []), ...peerSpans.filter(candidate => (
    candidate.id !== span.id
    && !explicitChildren.has(candidate.id)
    && (SPAN_DETAIL_LEVEL[candidate.span_type] ?? 3) > detailLevel
  ))]
  const intervals = candidates.flatMap((child) => {
    const childStart = Date.parse(child.started_time || '')
    if (!Number.isFinite(childStart)) return []
    const explicitEnd = Date.parse(child.ended_time || '')
    const childEnd = Number.isFinite(explicitEnd)
      ? explicitEnd
      : childStart + Math.max(Number(child.duration_ms) || 0, 0)
    const clippedStart = Math.max(startMs, childStart)
    const clippedEnd = Math.min(endMs, childEnd)
    return clippedEnd > clippedStart ? [[clippedStart, clippedEnd]] : []
  }).sort((a, b) => a[0] - b[0])
  if (!intervals.length) return durationMs

  let coveredMs = 0
  let [rangeStart, rangeEnd] = intervals[0]
  for (const [nextStart, nextEnd] of intervals.slice(1)) {
    if (nextStart <= rangeEnd) {
      rangeEnd = Math.max(rangeEnd, nextEnd)
    } else {
      coveredMs += rangeEnd - rangeStart
      rangeStart = nextStart
      rangeEnd = nextEnd
    }
  }
  coveredMs += rangeEnd - rangeStart
  return Math.max(Math.round(durationMs - coveredMs), 0)
}

export function filterTraceTree(nodes, filter, highLatencyThreshold) {
  if (filter === 'all') return nodes
  return nodes.flatMap((node) => {
    const children = filterTraceTree(node.children || [], filter, highLatencyThreshold)
    const matches = traceNodeMatches(node, filter, highLatencyThreshold)
    if (!matches && !children.length) return []
    return [{ ...node, children }]
  })
}

export function filterTraceRows(rows, filter, highLatencyThreshold) {
  if (filter === 'all') return rows
  return rows.filter(row => traceNodeMatches(row.span, filter, highLatencyThreshold))
}

function spanInterval(span) {
  const start = Date.parse(span?.started_time || '')
  if (!Number.isFinite(start)) return null
  const explicitEnd = Date.parse(span?.ended_time || '')
  const end = Number.isFinite(explicitEnd)
    ? explicitEnd
    : start + Math.max(Number(span?.duration_ms) || 0, 0)
  return { start, end: Math.max(end, start) }
}

function peakConcurrency(items) {
  const events = items.flatMap(item => ([
    { time: item.interval.start, delta: 1 },
    { time: item.interval.end, delta: -1 },
  ])).sort((left, right) => left.time - right.time || left.delta - right.delta)
  let active = 0
  let peak = 0
  for (const event of events) {
    active += event.delta
    peak = Math.max(peak, active)
  }
  return peak
}

export function annotateTraceConcurrency(nodes) {
  let groupCount = 0
  let maxConcurrency = 1

  function annotateLevel(sourceNodes, parentPath = 'root') {
    const annotated = (sourceNodes || []).map(node => ({
      ...node,
      children: annotateLevel(node.children || [], `${parentPath}/${node.id}`),
    }))
    const timed = annotated
      .map((node, index) => ({ node, index, interval: spanInterval(node) }))
      .filter(item => item.interval && item.interval.end > item.interval.start)
      .sort((left, right) => left.interval.start - right.interval.start || right.interval.end - left.interval.end)

    let group = []
    let groupEnd = -Infinity
    const finalize = () => {
      if (group.length >= 2) {
        const peak = peakConcurrency(group)
        if (peak >= 2) {
          groupCount += 1
          maxConcurrency = Math.max(maxConcurrency, peak)
          const groupId = `${parentPath}:parallel-${groupCount}`
          const start = Math.min(...group.map(item => item.interval.start))
          const end = Math.max(...group.map(item => item.interval.end))
          group.forEach((item, branchIndex) => {
            annotated[item.index] = {
              ...annotated[item.index],
              parallelGroup: {
                id: groupId,
                branchIndex: branchIndex + 1,
                spanCount: group.length,
                peak,
                start,
                end,
                first: branchIndex === 0,
                last: branchIndex === group.length - 1,
              },
            }
          })
        }
      }
      group = []
      groupEnd = -Infinity
    }

    for (const item of timed) {
      if (!group.length || item.interval.start < groupEnd) {
        group.push(item)
        groupEnd = Math.max(groupEnd, item.interval.end)
      } else {
        finalize()
        group = [item]
        groupEnd = item.interval.end
      }
    }
    finalize()
    return annotated
  }

  const tree = annotateLevel(nodes)
  return { tree, groupCount, maxConcurrency }
}

function traceNodeMatches(node, filter, highLatencyThreshold) {
  if (filter === 'errors') return ['failed', 'denied', 'abandoned'].includes(node.status)
  if (filter === 'slow') return highLatencyThreshold > 0 && (Number(node.duration_ms) || 0) >= highLatencyThreshold
  if (filter === 'tools') return ['tool_call', 'tool_execution'].includes(node.span_type)
  if (filter === 'subagents') return isSubagentTraceSpan(node)
  return true
}

function percentileThreshold(sortedValues, percentile) {
  if (!sortedValues.length) return 0
  const index = Math.min(Math.floor(sortedValues.length * percentile), sortedValues.length - 1)
  return sortedValues[index]
}

function durationBand(durationMs, thresholds) {
  if (!durationMs) return 'none'
  if (thresholds.p90 && durationMs >= thresholds.p90) return 'hot'
  if (thresholds.p75 && durationMs >= thresholds.p75) return 'high'
  if (thresholds.p50 && durationMs >= thresholds.p50) return 'medium'
  return 'low'
}
