import { ref, computed, watch } from 'vue'
import { useSession } from '@entities/session'
import { listModels, getProjectUsage } from '@entities/session'

const DEFAULT_CONTEXT_SIZE = 200000

// Cached model context sizes from backend
const modelContextSizes = ref({})
const projectUsageSummary = ref(null)
let usageFetchKey = ''
let _usageSeq = 0
let _modelsPromise = null


async function ensureModelsFetched() {
  if (_modelsPromise) return _modelsPromise
  _modelsPromise = (async () => {
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
    } catch {
      _modelsPromise = null
    }
  })()
  return _modelsPromise
}

export function useSessionStats() {
  const { session, messages, queryHistory } = useSession()

  ensureModelsFetched()

  async function refreshUsage() {
    const current = session.value
    if (!current?.session_id) return
    const key = `${current.session_id}:${current.project_id || ''}:${current.usage?.input_tokens || 0}:${current.usage?.output_tokens || 0}`
    if (key === usageFetchKey) return
    const prevKey = usageFetchKey
    usageFetchKey = key
    const seq = ++_usageSeq
    try {
      const projectUsage = await (
        current.project_id ? getProjectUsage(current.project_id, true) : Promise.resolve(null)
      )
      if (seq !== _usageSeq) return
      projectUsageSummary.value = projectUsage
    } catch {
      if (seq === _usageSeq) usageFetchKey = prevKey
    }
  }

  watch(
    () => [session.value?.session_id, session.value?.project_id, session.value?.usage?.input_tokens, session.value?.usage?.output_tokens],
    refreshUsage,
    { immediate: true },
  )


  const gitBranch = computed(() => session.value?.git_branch || '')

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

  return {
    gitBranch,
    contextUsage,
    toolStats,
    projectUsageSummary,
  }
}
