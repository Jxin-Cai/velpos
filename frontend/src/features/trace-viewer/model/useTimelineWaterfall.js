import { computed } from 'vue'

/**
 * Computes waterfall (mini gantt chart) segments from the list of tasks.
 * Each loop becomes a colored segment whose width represents time duration
 * and position represents when it started relative to the entire run.
 */
export function useTimelineWaterfall(tasks) {
  return computed(() => {
    const allLoops = tasks.value.flatMap(task => (task.loops || []).filter(l => l.started_time))
    if (allLoops.length < 2) return { segments: [], totalMs: 0 }

    const times = allLoops.map(l => new Date(l.started_time).getTime())
    const endTimes = allLoops.map(l => new Date(l.ended_time || l.started_time).getTime())
    const earliest = Math.min(...times)
    const latest = Math.max(...endTimes)
    const totalMs = latest - earliest || 1

    const segments = allLoops.map(loop => {
      const start = new Date(loop.started_time).getTime()
      const duration = loop.duration_ms || 0
      const toolNames = loop.tool_names || []
      const usage = loop.usage || {}
      const tokens = (usage.input_tokens || 0) + (usage.output_tokens || 0)
      const errorCount = loop.error_count || 0

      // Build a descriptive label for hover
      const name = toolNames.length
        ? toolNames.slice(0, 3).join(', ') + (toolNames.length > 3 ? ` +${toolNames.length - 3}` : '')
        : 'Model response'

      return {
        id: loop.id,
        startPct: ((start - earliest) / totalMs) * 100,
        widthPct: Math.max((duration / totalMs) * 100, 0.8),
        type: toolNames.length ? 'tool' : 'model',
        hasError: errorCount > 0,
        sequence: loop.sequence || 0,
        // Info for tooltip
        name,
        durationMs: duration,
        tokens,
        errorCount,
        model: loop.model || '',
      }
    })

    return { segments, totalMs }
  })
}
