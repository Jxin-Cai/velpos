import { downloadJsonReport, safeFilenamePart } from './executionErrorExport.js'

const DETAIL_PAGE_SIZE = 500
const EVENT_PAGE_SIZE = 5000
const DETAIL_EXPORT_CONCURRENCY = 4

export async function buildExecutionTraceReport({
  sessionId,
  runId,
  rootTree,
  fetchTree,
  fetchDetail,
  fetchTraceTree,
  fetchExecutionEvents,
  fetchTelemetrySummary,
  exportedAt = new Date().toISOString(),
}) {
  const agents = []
  const visitedAgentSpans = new Set()

  async function visitTree(tree, agentSpanId = null) {
    if (!tree) return
    const loops = (tree.tasks || []).flatMap(task => task.loops || [])
    const loopDetails = await mapWithConcurrency(
      loops,
      DETAIL_EXPORT_CONCURRENCY,
      async loop => ({
        loop_id: loop.id,
        events: await fetchAllLoopEvents({
          sessionId,
          runId,
          loopId: loop.id,
          agentSpanId,
          fetchDetail,
        }),
      }),
    )
    agents.push({ agent_span_id: agentSpanId, tree, loop_details: loopDetails })

    for (const subagent of collectSubagents(tree)) {
      const spanId = subagent?.span_id
      if (!spanId || visitedAgentSpans.has(spanId)) continue
      visitedAgentSpans.add(spanId)
      await visitTree(await fetchTree(sessionId, runId, spanId), spanId)
    }
  }

  const [rawTrace, telemetry, executionEvents] = await Promise.all([
    fetchTraceTree(sessionId, runId),
    fetchTelemetrySummary(sessionId, runId),
    fetchAllExecutionEvents({ sessionId, runId, fetchExecutionEvents }),
  ])
  await visitTree(rootTree)

  return {
    format: 'velpos.execution-trace.v2',
    session_id: sessionId,
    run_id: runId,
    exported_at: exportedAt,
    summary: {
      span_count: rawTrace?.span_count || 0,
      execution_event_count: executionEvents.length,
      agent_count: agents.length,
      log_event_count: telemetry?.log_event_count || 0,
      metric_sample_count: telemetry?.metric_sample_count || 0,
    },
    telemetry,
    raw_trace: rawTrace,
    execution_events: executionEvents,
    agents,
  }
}

export function downloadExecutionTraceReport(report) {
  downloadJsonReport(
    report,
    `execution-trace-${safeFilenamePart(report.session_id)}-${safeFilenamePart(report.run_id)}.json`,
  )
}

async function fetchAllExecutionEvents({ sessionId, runId, fetchExecutionEvents }) {
  const events = []
  let cursor = 0
  while (true) {
    const page = await fetchExecutionEvents(sessionId, runId, cursor, EVENT_PAGE_SIZE)
    events.push(...(page?.events || []))
    if (!page?.has_more) return events
    const nextCursor = Number(page.next_sequence)
    if (!Number.isFinite(nextCursor) || nextCursor <= cursor) {
      throw new Error('Execution event export cursor did not advance')
    }
    cursor = nextCursor
  }
}

async function fetchAllLoopEvents({ sessionId, runId, loopId, agentSpanId, fetchDetail }) {
  const events = []
  let cursor = 0
  do {
    const page = await fetchDetail(
      sessionId,
      runId,
      loopId,
      agentSpanId,
      cursor,
      DETAIL_PAGE_SIZE,
    )
    events.push(...(page?.items || []))
    cursor = page?.next_cursor ?? null
  } while (cursor !== null)
  return events
}

function collectSubagents(tree) {
  const bySpanId = new Map()
  const candidates = [
    ...(tree?.subagents || []),
    ...(tree?.tasks || []).flatMap(task => (
      (task.loops || []).flatMap(loop => loop.subagents || [])
    )),
  ]
  for (const subagent of candidates) {
    if (subagent?.span_id) bySpanId.set(subagent.span_id, subagent)
  }
  return [...bySpanId.values()]
}

async function mapWithConcurrency(items, concurrency, mapper) {
  if (!items.length) return []
  const results = new Array(items.length)
  let nextIndex = 0

  async function worker() {
    while (nextIndex < items.length) {
      const currentIndex = nextIndex
      nextIndex += 1
      results[currentIndex] = await mapper(items[currentIndex], currentIndex)
    }
  }

  const workerCount = Math.min(concurrency, items.length)
  await Promise.all(Array.from({ length: workerCount }, () => worker()))
  return results
}
