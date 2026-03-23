import { ref, computed } from 'vue'
import { useSession } from '@entities/session'
import { listModels } from '@entities/session'

const DEFAULT_CONTEXT_SIZE = 200000

// Cached model context sizes from backend
const modelContextSizes = ref({})
let modelsFetched = false

async function ensureModelsFetched() {
  if (modelsFetched) return
  try {
    const res = await listModels()
    const models = res || []
    const sizes = {}
    for (const m of models) {
      if (m.value && m.context_window) {
        sizes[m.value] = m.context_window
      }
    }
    modelContextSizes.value = sizes
    modelsFetched = true
  } catch {
    // keep defaults — modelsFetched stays false so next call retries
  }
}

export function useSessionStats() {
  const { session, messages, queryHistory, status } = useSession()

  // Lazy-load models on first use
  ensureModelsFetched()

  // Git branch: from session data if available
  const gitBranch = computed(() => session.value?.git_branch || '')

  // Last query duration
  const lastQueryDuration = computed(() => {
    if (!queryHistory.value.length) return null
    const last = queryHistory.value[queryHistory.value.length - 1]
    return last.duration_ms || null
  })

  // Context usage ratio
  // Uses last query's input_tokens as the best estimate of current context
  // window consumption (aligns with claude-hud: context = input_tokens only,
  // output_tokens are NOT part of context window consumption).
  const contextUsage = computed(() => {
    const model = session.value?.model || ''
    const maxTokens = modelContextSizes.value[model] || DEFAULT_CONTEXT_SIZE

    // Best estimate: last query's input_tokens from backend (persisted across reconnects)
    // This represents the actual context window size at the last API call.
    const lastInputTokens = session.value?.last_input_tokens || 0

    let currentContextTokens = 0

    // Priority 1: Use last queryHistory entry's input_tokens (live session fallback)
    if (queryHistory.value.length > 0) {
      const lastQuery = queryHistory.value[queryHistory.value.length - 1]
      const lastQueryInput = lastQuery?.usage?.input_tokens || 0
      if (lastQueryInput > 0) {
        currentContextTokens = lastQueryInput
      }
    }

    // Priority 2 (higher): Use backend-persisted last_input_tokens.
    // This is per-turn context (from AssistantMessage.usage), far more
    // accurate than the cumulative total in queryHistory.
    if (lastInputTokens > 0) {
      currentContextTokens = lastInputTokens
    }

    // No Priority 3 fallback — cumulative usage is misleading for context display

    const ratio = maxTokens > 0 ? currentContextTokens / maxTokens : 0
    return {
      current: currentContextTokens,
      max: maxTokens,
      ratio: Math.min(ratio, 1),
      percent: Math.min(Math.round(ratio * 100), 100),
    }
  })

  // Tool/skill usage stats: count tool_use by name
  const toolStats = computed(() => {
    const counts = {}
    for (const msg of messages.value) {
      if (msg.type === 'assistant' && msg.content?.blocks) {
        for (const block of msg.content.blocks) {
          if (block.type === 'tool_use' && block.name) {
            counts[block.name] = (counts[block.name] || 0) + 1
          }
        }
      }
    }
    // Sort by count descending
    return Object.entries(counts)
      .sort((a, b) => b[1] - a[1])
      .map(([name, count]) => ({ name, count }))
  })

  // Active subagents: track from system messages (task_started / task_progress / task_notification)
  const activeSubagents = computed(() => {
    const tasks = {}
    const now = Date.now()
    for (const msg of messages.value) {
      if (msg.type !== 'system' || !msg.content) continue
      const { subtype, task_id, description, status: taskStatus, summary } = msg.content
      if (!task_id) continue

      if (subtype === 'task_started') {
        tasks[task_id] = {
          task_id,
          description: description || '',
          startTime: msg.timestamp || now,
          status: 'running',
        }
      } else if (subtype === 'task_progress') {
        if (tasks[task_id]) {
          if (description) tasks[task_id].description = description
        } else {
          tasks[task_id] = {
            task_id,
            description: description || '',
            startTime: now,
            status: 'running',
          }
        }
      } else if (subtype === 'task_notification') {
        if (tasks[task_id]) {
          tasks[task_id].status = taskStatus || 'done'
        }
      }
    }
    // Return only running tasks
    return Object.values(tasks).filter(t => t.status === 'running')
  })

  return {
    gitBranch,
    lastQueryDuration,
    contextUsage,
    toolStats,
    activeSubagents,
  }
}
