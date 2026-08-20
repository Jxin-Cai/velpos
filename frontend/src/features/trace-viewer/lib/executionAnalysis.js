export const ExecutionPresentation = Object.freeze({
  FLOW: 'flow',
  DURATION: 'duration',
  TOKENS: 'tokens',
})

export function executionStepTokens(loop) {
  const usage = loop?.usage || {}
  return Math.max(Number(usage.input_tokens) || 0, 0)
    + Math.max(Number(usage.output_tokens) || 0, 0)
}

export function executionMetricPercent(value, maximum) {
  const metric = Math.max(Number(value) || 0, 0)
  const scale = Math.max(Number(maximum) || 0, 0)
  if (!metric || !scale) return 0
  return Math.min(metric / scale * 100, 100)
}

export function taskSubagents(task, executionSubagents = []) {
  const byToolUseId = new Map((executionSubagents || [])
    .filter(subagent => subagent?.tool_use_id)
    .map(subagent => [subagent.tool_use_id, subagent]))
  const result = new Map()
  for (const loop of task?.loops || []) {
    const candidates = loop.subagents?.length
      ? loop.subagents
      : (loop.subagent_tool_use_ids || []).map(toolUseId => byToolUseId.get(toolUseId)).filter(Boolean)
    for (const subagent of candidates) {
      const key = subagent?.tool_use_id || subagent?.span_id
      if (key && !result.has(key)) result.set(key, subagent)
    }
  }
  return [...result.values()]
}

// Subagents are listed per task and per step, which hides the order the agent
// actually delegated work in. Walking tasks and steps in execution order
// rebuilds that call chain, so a reader can follow the handoffs.
export function buildSubagentChain(tasks, executionSubagents = []) {
  const byToolUseId = new Map((executionSubagents || [])
    .filter(subagent => subagent?.tool_use_id)
    .map(subagent => [subagent.tool_use_id, subagent]))
  const chain = new Map()

  for (const [taskIndex, task] of (tasks || []).entries()) {
    for (const [stepIndex, loop] of (task?.loops || []).entries()) {
      const candidates = loop.subagents?.length
        ? loop.subagents
        : (loop.subagent_tool_use_ids || []).map(toolUseId => byToolUseId.get(toolUseId)).filter(Boolean)
      for (const subagent of candidates) {
        const key = subagent?.tool_use_id || subagent?.span_id
        if (!key || chain.has(key)) continue
        chain.set(key, {
          ...byToolUseId.get(subagent.tool_use_id),
          ...subagent,
          key,
          taskSequence: task.sequence || taskIndex + 1,
          stepSequence: loop.sequence || stepIndex + 1,
        })
      }
    }
  }

  // A subagent whose invoking step was filtered out, or was never linked to a
  // step, still belongs to the run and would otherwise disappear.
  for (const subagent of executionSubagents || []) {
    const key = subagent?.tool_use_id || subagent?.span_id
    if (!key || chain.has(key)) continue
    chain.set(key, { ...subagent, key, taskSequence: null, stepSequence: null })
  }

  return [...chain.values()].map((item, index) => ({ ...item, order: index + 1 }))
}

function timestamp(value) {
  const parsed = Date.parse(value || '')
  return Number.isFinite(parsed) ? parsed : null
}

export function buildExecutionTaskRows(tasks, executionSubagents = []) {
  const rows = (tasks || []).map((task, taskIndex) => {
    const steps = (task.loops || []).map((loop, stepIndex) => ({
      loop,
      sequence: loop.sequence || stepIndex + 1,
      durationMs: Math.max(Number(loop.duration_ms) || 0, 0),
      tokens: executionStepTokens(loop),
    }))
    const starts = steps.map(step => timestamp(step.loop.started_time)).filter(value => value != null)
    const ends = steps.map(step => timestamp(step.loop.ended_time)).filter(value => value != null)
    const activeDurationMs = steps.reduce((total, step) => total + step.durationMs, 0)
    const wallDurationMs = starts.length && ends.length
      ? Math.max(Math.max(...ends) - Math.min(...starts), 0)
      : activeDurationMs
    return {
      task,
      sequence: task.sequence || taskIndex + 1,
      steps,
      subagents: taskSubagents(task, executionSubagents),
      activeDurationMs,
      wallDurationMs,
      tokens: steps.reduce((total, step) => total + step.tokens, 0),
    }
  })

  const totalTokens = rows.reduce((total, row) => total + row.tokens, 0)
  const totalActiveDurationMs = rows.reduce((total, row) => total + row.activeDurationMs, 0)
  return rows.map(row => ({
    ...row,
    tokenShare: totalTokens ? row.tokens / totalTokens : 0,
    durationShare: totalActiveDurationMs ? row.activeDurationMs / totalActiveDurationMs : 0,
  }))
}

export function rankExecutionTasks(rows, mode) {
  const metric = mode === ExecutionPresentation.TOKENS ? 'tokens' : 'activeDurationMs'
  return [...(rows || [])]
    .sort((left, right) => right[metric] - left[metric] || left.sequence - right.sequence)
    .map(row => ({
      ...row,
      steps: [...row.steps].sort((left, right) => (
        mode === ExecutionPresentation.TOKENS
          ? right.tokens - left.tokens || left.sequence - right.sequence
          : right.durationMs - left.durationMs || left.sequence - right.sequence
      )),
    }))
}
