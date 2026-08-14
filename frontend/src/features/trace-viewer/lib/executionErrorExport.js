const DETAIL_PAGE_SIZE = 500

export async function buildExecutionErrorReport({
  sessionId,
  runId,
  rootTree,
  fetchTree,
  fetchDetail,
  exportedAt = new Date().toISOString(),
}) {
  const errorSteps = []
  const agentErrors = []
  const visitedAgentSpans = new Set()
  let scannedAgentCount = 0

  async function visitTree(tree, agentSpanId = null) {
    if (!tree) return
    scannedAgentCount += 1
    if (tree.error_message) {
      agentErrors.push({
        agent_id: tree.agent_id || null,
        agent_span_id: agentSpanId,
        error_message: tree.error_message,
      })
    }

    for (const task of tree.tasks || []) {
      for (const loop of task.loops || []) {
        if ((loop.error_count || 0) <= 0 && !loop.error_message) continue
        const allEvents = await fetchAllLoopEvents({
          sessionId,
          runId,
          loopId: loop.id,
          agentSpanId,
          fetchDetail,
        })
        const events = collectErrorContext(allEvents)
        errorSteps.push({
          agent_id: tree.agent_id || null,
          agent_span_id: agentSpanId,
          task: {
            id: task.id,
            subject: task.subject,
            description: task.description || null,
            status: task.status,
          },
          step: {
            id: loop.id,
            sequence: loop.sequence,
            model: loop.model || null,
            tool_names: loop.tool_names || [],
            started_time: loop.started_time || null,
            ended_time: loop.ended_time || null,
            duration_ms: loop.duration_ms || 0,
            error_message: loop.error_message || null,
            error_count: loop.error_count || 0,
            error_summary: loop.error_summary || {},
          },
          events,
          error_events: events.filter(event => event?.is_error),
        })
      }
    }

    for (const subagent of collectSubagents(tree)) {
      const spanId = subagent?.span_id
      if (!spanId || visitedAgentSpans.has(spanId)) continue
      visitedAgentSpans.add(spanId)
      const childTree = await fetchTree(sessionId, runId, spanId)
      await visitTree(childTree, spanId)
    }
  }

  await visitTree(rootTree)

  const stepErrorCount = errorSteps.reduce(
    (count, item) => count + Math.max(item.step.error_count, item.step.error_message ? 1 : 0),
    0,
  )
  const runErrorCount = agentErrors.length

  return {
    format: 'velpos.execution-errors.v2',
    session_id: sessionId,
    run_id: runId,
    exported_at: exportedAt,
    summary: {
      error_count: stepErrorCount + runErrorCount,
      error_step_count: errorSteps.length,
      scanned_agent_count: scannedAgentCount,
    },
    run_error: rootTree?.error_message || null,
    agent_errors: agentErrors,
    provenance: rootTree?.provenance || null,
    errors: errorSteps,
  }
}

export async function countExecutionErrors({ sessionId, runId, rootTree, fetchTree }) {
  let count = 0
  const visitedAgentSpans = new Set()

  async function visitTree(tree) {
    if (!tree) return
    if (tree.error_message) count += 1
    for (const task of tree.tasks || []) {
      for (const loop of task.loops || []) {
        count += Math.max(loop.error_count || 0, loop.error_message ? 1 : 0)
      }
    }
    for (const subagent of collectSubagents(tree)) {
      const spanId = subagent?.span_id
      if (!spanId || visitedAgentSpans.has(spanId)) continue
      visitedAgentSpans.add(spanId)
      await visitTree(await fetchTree(sessionId, runId, spanId))
    }
  }

  await visitTree(rootTree)
  return count
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

function collectErrorContext(events) {
  const errorEvents = events.filter(event => event?.is_error)
  const failedToolUseIds = new Set(
    errorEvents.map(event => event.tool_use_id).filter(Boolean),
  )
  return events.filter(event => (
    event?.is_error
    || (event?.type === 'tool_use' && failedToolUseIds.has(event.tool_use_id))
  ))
}

export function downloadExecutionErrorReport(report) {
  downloadJsonReport(
    report,
    `execution-errors-${safeFilenamePart(report.session_id)}-${safeFilenamePart(report.run_id)}.json`,
  )
}

export function downloadJsonReport(report, filename) {
  const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

export function safeFilenamePart(value) {
  return String(value || 'unknown').replace(/[^a-zA-Z0-9._-]+/g, '-')
}
