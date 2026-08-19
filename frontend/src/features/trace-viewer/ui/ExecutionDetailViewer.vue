<script setup>
import { computed } from 'vue'
import { formatDuration as _formatDuration } from '@shared/lib/formatTime'
import SpanPayloadViewer from './SpanPayloadViewer.vue'
import InlineSubagentTree from './InlineSubagentTree.vue'

const props = defineProps({
  loopId: { type: String, default: null },
  loop: { type: Object, default: null },
  detail: { type: Object, default: null },
  loadState: { type: String, default: 'idle' },
  provenance: { type: Object, default: null },
  agentSpanId: { type: String, default: null },
  getInlineSubagentState: { type: Function, default: () => null },
  getLoopDetail: { type: Function, default: () => null },
  getLoopLoadState: { type: Function, default: () => 'idle' },
  loadLoopDetail: { type: Function, default: async () => {} },
  loadMoreEvents: { type: Function, default: async () => {} },
})

const emit = defineEmits(['toggle-inline-subagent'])

const events = computed(() => props.detail?.items || [])
const toolResultsById = computed(() => new Map(
  events.value
    .filter(event => event.type === 'tool_result' && event.tool_use_id)
    .map(event => [event.tool_use_id, event]),
))
const pairedResultIds = computed(() => new Set(
  events.value
    .filter(event => event.type === 'tool_use' && event.tool_use_id)
    .map(event => event.tool_use_id),
))
const subagentToolIds = computed(() => new Set(
  events.value
    .filter(event => event.type === 'subagent' && event.metadata?.tool_use_id)
    .map(event => event.metadata.tool_use_id),
))

const modelOutputBySource = computed(() => new Map(
  events.value
    .filter(event => (event.type === 'model_output' || event.type === 'assistant_message') && event.source_uuid)
    .map(event => [event.source_uuid, event]),
))
const modelInputSources = computed(() => new Set(
  events.value
    .filter(event => (event.type === 'model_input' || event.type === 'user_message') && event.source_uuid)
    .map(event => event.source_uuid),
))
// Older transcript records may not carry a source UUID. Pair the next model
// output in that case so the UI still presents one complete model turn.
const modelOutputByInputIndex = computed(() => {
  const pairs = new Map()
  let nextOutputIndex = null
  for (let index = events.value.length - 1; index >= 0; index -= 1) {
    const event = events.value[index]
    const isInput = event.type === 'model_input' || event.type === 'user_message'
    if (isInput && !event.source_uuid && nextOutputIndex != null) {
      pairs.set(index, nextOutputIndex)
    }
    if (event.type === 'model_output' || event.type === 'assistant_message') {
      nextOutputIndex = index
    }
  }
  return pairs
})
const pairedModelOutputIndices = computed(() => new Set(modelOutputByInputIndex.value.values()))
const failureMessage = computed(() => {
  if (props.loop?.error_message) return props.loop.error_message
  return events.value.find(event => event.is_error && event.error_message)?.error_message || null
})

// Retry chain tracking: count retries per original tool_use_id
const retryChains = computed(() => {
  const chains = new Map()
  for (const event of events.value) {
    if (event.type === 'tool_use' && event.retry_of_tool_use_id) {
      const count = chains.get(event.retry_of_tool_use_id) || 0
      chains.set(event.retry_of_tool_use_id, count + 1)
    }
  }
  return chains
})

const retrySequence = computed(() => {
  const sequence = new Map()
  const counters = new Map()
  for (const event of events.value) {
    if (event.type === 'tool_use' && event.retry_of_tool_use_id) {
      const count = (counters.get(event.retry_of_tool_use_id) || 0) + 1
      counters.set(event.retry_of_tool_use_id, count)
      sequence.set(event.tool_use_id, count)
    }
  }
  return sequence
})

const THINKING_KEYWORDS = ['retry', 'error', 'fallback', 'failed', 'alternative', 'workaround']

const eventItems = computed(() => events.value.flatMap((event, sourceIndex) => {
  if (event.type === 'tool_result' && pairedResultIds.value.has(event.tool_use_id)) return []
  if (event.type === 'tool_use' && subagentToolIds.value.has(event.tool_use_id)) return []

  const base = {
    id: `${event.source_uuid || 'event'}-${event.type}-${sourceIndex}`,
    sourceIndex,
    sourceUuid: event.source_uuid,
    timestamp: event.timestamp,
    isError: Boolean(event.is_error),
    errorMessage: event.error_message || null,
    errorCategory: event.error_category || null,
  }

  if (event.type === 'tool_use') {
    const result = toolResultsById.value.get(event.tool_use_id)
    const retryOf = event.retry_of_tool_use_id || null
    const retryNum = retrySequence.value.get(event.tool_use_id) || 0
    const retriedCount = retryChains.value.get(event.tool_use_id) || 0
    return [{
      ...base,
      kind: 'tool',
      label: 'Tool call',
      title: event.tool_name || 'Unknown tool',
      input: event.content,
      output: result?.content,
      endedTime: result?.timestamp,
      isError: Boolean(event.is_error || result?.is_error),
      errorCategory: event.error_category || result?.error_category || null,
      toolUseId: event.tool_use_id,
      retryOf,
      retryNum,
      retriedCount,
    }]
  }

  if (event.type === 'subagent') {
    const result = toolResultsById.value.get(event.metadata?.tool_use_id)
    return [{
      ...base,
      kind: 'subagent',
      label: 'Subagent',
      title: event.metadata?.subagent || 'Agent',
      input: event.content,
      output: result?.content,
      endedTime: result?.timestamp,
      metadata: event.metadata || {},
    }]
  }

  if (event.type === 'model_input' || event.type === 'user_message') {
    const fallbackOutputIndex = modelOutputByInputIndex.value.get(sourceIndex)
    const output = event.source_uuid
      ? modelOutputBySource.value.get(event.source_uuid)
      : (fallbackOutputIndex == null ? null : events.value[fallbackOutputIndex])
    return [{
      ...base,
      kind: 'model',
      label: 'Model turn',
      title: props.loop?.model || 'Input and output',
      input: event.content,
      output: output?.content,
      endedTime: output?.timestamp,
      inputSummary: event.metadata?.input_summary || null,
    }]
  }

  if (event.type === 'model_output' || event.type === 'assistant_message') {
    if (event.source_uuid && modelInputSources.value.has(event.source_uuid)) return []
    if (!event.source_uuid && pairedModelOutputIndices.value.has(sourceIndex)) return []
    return [{
      ...base,
      kind: 'output',
      label: 'Model output',
      title: props.loop?.model || 'Assistant response',
      output: event.content,
    }]
  }

  if (event.type === 'thinking') {
    const planning = event.metadata?.phase === 'planning'
    const text = typeof event.content === 'string' ? event.content : ''
    const keywords = THINKING_KEYWORDS.filter(kw => text.toLowerCase().includes(kw))
    const preview = text.slice(0, 200) + (text.length > 200 ? '...' : '')
    return [{
      ...base,
      kind: 'thinking',
      label: planning ? 'Planning' : 'Thinking',
      title: planning ? 'Plan before task execution' : 'Reasoning',
      output: event.content,
      thinkingPreview: preview,
      thinkingKeywords: keywords,
    }]
  }

  return [{ ...base, kind: 'event', label: event.type, title: 'Recorded event', output: event.content }]
}))

const total = computed(() => props.detail?.total || 0)
const toolCallCount = computed(() => events.value.filter(event => event.type === 'tool_use').length)
const hasMore = computed(() => props.detail?.next_cursor != null)
const tokenBreakdown = computed(() => {
  const usage = props.loop?.usage || {}
  const input = usage.input_tokens || 0
  const output = usage.output_tokens || 0
  const cacheRead = usage.cache_read_input_tokens || 0
  const cacheWrite = usage.cache_creation_input_tokens || 0
  // Total input context = new input tokens + cache-served tokens
  const totalInput = input + cacheRead
  const cacheHitPct = totalInput > 0 ? Math.round(cacheRead / totalInput * 100) : 0
  return { input, output, cacheWrite, cacheRead, total: input + output, cacheHitPct }
})
const tokenTooltip = computed(() => {
  const b = tokenBreakdown.value
  const parts = [`Input: ${formatTokensK(b.input)}`, `Output: ${formatTokensK(b.output)}`]
  if (b.cacheWrite) parts.push(`Cache write: ${formatTokensK(b.cacheWrite)}`)
  if (b.cacheRead) parts.push(`Cache read: ${formatTokensK(b.cacheRead)}`)
  return parts.join(' · ')
})
const isReconstructed = computed(() => props.provenance?.reconstructed_from_transcript)

function formatTokensK(n) {
  if (!n) return '0'
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`
  return String(n)
}

function formatChars(n) {
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`
  return String(n)
}

function errorCategoryLabel(category) {
  const map = {
    permission_denied: 'Permission',
    timeout: 'Timeout',
    invalid_input: 'Invalid input',
    execution_failure: 'Failed',
    network_error: 'Network',
  }
  return map[category] || 'Error'
}

const formatDuration = (ms) => _formatDuration(ms, { zeroValue: '—' })

function formatTime(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return new Intl.DateTimeFormat(undefined, {
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  }).format(date)
}

function itemDuration(item) {
  if (!item.timestamp || !item.endedTime) return ''
  const duration = new Date(item.endedTime).getTime() - new Date(item.timestamp).getTime()
  return duration >= 0 ? formatDuration(duration) : ''
}
</script>

<template>
  <div class="exec-detail">
    <div v-if="loadState === 'loading'" class="detail-state">
      <span class="detail-spinner" aria-hidden="true"></span>
      <span>Loading recorded events…</span>
    </div>

    <div v-else-if="loadState === 'error'" class="detail-state detail-state--error">
      <span>Failed to load step detail</span>
      <span v-if="detail?.error" class="detail-error-msg">{{ detail.error }}</span>
    </div>

    <div v-else-if="!loopId" class="detail-state">
      <p>Select a step to inspect its input, output, and tool activity.</p>
    </div>

    <template v-else>
      <section class="step-overview">
        <div class="step-overview-main">
          <span class="step-index">{{ loop?.sequence || '—' }}</span>
          <div>
            <div class="step-kicker">Execution step</div>
            <h3 class="step-title">{{ loop?.tool_names?.join(' + ') || 'Model response' }}</h3>
            <p class="step-subtitle">
              <span v-if="loop?.started_time">Started {{ formatTime(loop.started_time) }}</span>
              <span v-if="loop?.model">{{ loop.model }}</span>
            </p>
          </div>
        </div>
        <dl class="step-stats">
          <div><dt>Duration</dt><dd>{{ formatDuration(loop?.duration_ms) }}</dd></div>
          <div><dt>Events</dt><dd>{{ total }}</dd></div>
          <div><dt>Tools</dt><dd>{{ toolCallCount }}</dd></div>
          <div>
            <dt>Tokens</dt>
            <dd :title="tokenTooltip">
              {{ formatTokensK(tokenBreakdown.total) }}
              <span v-if="tokenBreakdown.cacheHitPct > 0" class="cache-hit-badge">{{ tokenBreakdown.cacheHitPct }}% cached</span>
            </dd>
          </div>
        </dl>
      </section>

      <div v-if="failureMessage" class="execution-error" role="alert">
        {{ failureMessage }}
      </div>

      <div v-if="isReconstructed" class="detail-provenance">
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
          <circle cx="8" cy="8" r="6.25"/><path d="M8 5v3.5M8 11h.01"/>
        </svg>
        <span>Reconstructed from transcript</span>
        <span v-if="provenance?.completeness && provenance.completeness !== 'complete'" class="provenance-tag">
          {{ provenance.completeness }}
        </span>
      </div>

      <div class="event-list-heading">
        <div>
          <h4>Recorded events</h4>
          <p>Model turns and tool calls are paired with their captured input and result payloads.</p>
        </div>
        <span v-if="hasMore" class="more-badge">{{ events.length }} / {{ total }} loaded</span>
      </div>

      <ol v-if="eventItems.length" class="recorded-event-list">
        <li v-for="item in eventItems" :key="item.id" class="recorded-event-item" :class="[`recorded-event-item--${item.kind}`, { 'has-keywords': item.thinkingKeywords?.length }]">
          <details class="event-card" :open="item.kind !== 'thinking'">
            <summary class="event-summary">
              <span class="event-icon" aria-hidden="true">
                <svg v-if="item.kind === 'tool'" viewBox="0 0 16 16"><path d="M6.5 3.5a3 3 0 0 0 3.8 3.8l-5.5 5.5-1.6-1.6 5.5-5.5a3 3 0 0 0 3.8-3.8L10.7 4.2 9.2 2.7z"/></svg>
                <svg v-else-if="item.kind === 'thinking'" viewBox="0 0 16 16"><path d="M8 2a4.5 4.5 0 0 0-2 8.5V12h4v-1.5A4.5 4.5 0 0 0 8 2z"/><path d="M6 13.5h4M7 15h2"/></svg>
                <svg v-else-if="item.kind === 'input'" viewBox="0 0 16 16"><path d="M3 8h9M8 4l4 4-4 4"/></svg>
                <svg v-else-if="item.kind === 'output'" viewBox="0 0 16 16"><path d="M13 8H4M8 4 4 8l4 4"/></svg>
                <svg v-else viewBox="0 0 16 16"><circle cx="8" cy="8" r="4"/></svg>
              </span>
              <span class="event-heading">
                <span class="event-label">{{ item.label }}</span>
                <strong>{{ item.title }}</strong>
                <span v-if="item.kind === 'thinking' && item.thinkingPreview" class="thinking-preview">{{ item.thinkingPreview }}</span>
              </span>
              <span class="event-timing">
                <span v-if="item.timestamp">{{ formatTime(item.timestamp) }}</span>
                <span v-if="itemDuration(item)">{{ itemDuration(item) }}</span>
              </span>
              <span v-if="item.retryNum" class="event-retry-flag">Retry #{{ item.retryNum }}</span>
              <span v-else-if="item.retriedCount" class="event-retried-flag">{{ item.retriedCount }} retries</span>
              <span v-if="item.isError" class="event-error-flag" :class="`error-cat--${item.errorCategory || 'unknown'}`">{{ errorCategoryLabel(item.errorCategory) }}</span>
              <span v-if="item.thinkingKeywords?.length" class="thinking-keywords">
                <span v-for="kw in item.thinkingKeywords" :key="kw" class="keyword-tag">{{ kw }}</span>
              </span>
              <svg class="summary-chevron" width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
                <path d="m4 6 4 4 4-4"/>
              </svg>
            </summary>

            <!-- Model input summary card -->
            <div v-if="item.kind === 'model' && item.inputSummary" class="input-summary-bar">
              <span class="summary-chip"><strong>{{ item.inputSummary.message_count }}</strong> messages</span>
              <span class="summary-chip"><strong>{{ formatChars(item.inputSummary.total_chars) }}</strong> chars</span>
              <span v-if="item.inputSummary.tool_result_count" class="summary-chip"><strong>{{ item.inputSummary.tool_result_count }}</strong> tool results</span>
              <span v-if="item.inputSummary.has_images" class="summary-chip">has images</span>
            </div>

            <div class="event-body" :class="{ 'event-body--split': item.input != null && item.output != null }">
              <SpanPayloadViewer v-if="item.input != null" :payload="item.input" label="Complete input" />
              <SpanPayloadViewer v-if="item.output != null" :payload="item.output" label="Complete output" />
              <div v-if="item.input == null && item.output == null" class="event-no-content">No payload was recorded for this event.</div>
            </div>

            <div v-if="item.kind === 'subagent'" class="subagent-actions">
              <button
                v-if="item.metadata?.span_id"
                class="inline-expand-btn"
                type="button"
                :aria-expanded="Boolean(getInlineSubagentState(item.metadata.span_id))"
                @click.stop="emit('toggle-inline-subagent', item.metadata.span_id)"
              >
                {{ getInlineSubagentState(item.metadata.span_id) ? 'Hide subagent tree' : 'Inspect subagent tree' }}
              </button>
              <span v-else class="inline-unavailable">Internal process unavailable for this subagent run</span>
              <div v-if="item.metadata?.span_id && getInlineSubagentState(item.metadata.span_id)" class="inline-subagent-section">
                <div v-if="getInlineSubagentState(item.metadata.span_id)?.loading" class="inline-state">Loading subagent tree…</div>
                <div v-else-if="getInlineSubagentState(item.metadata.span_id)?.error" class="inline-state inline-state--error">
                  {{ getInlineSubagentState(item.metadata.span_id).error }}
                </div>
                <InlineSubagentTree
                  v-else-if="getInlineSubagentState(item.metadata.span_id)?.tree"
                  :tree="getInlineSubagentState(item.metadata.span_id).tree"
                  :agent-span-id="item.metadata.span_id"
                  :get-loop-detail="getLoopDetail"
                  :get-loop-load-state="getLoopLoadState"
                  :load-loop-detail="loadLoopDetail"
                  :load-more-events="loadMoreEvents"
                />
              </div>
            </div>
          </details>
        </li>
      </ol>

      <div v-if="eventItems.length && (hasMore || detail?.moreError)" class="event-load-more">
        <button
          type="button"
          class="event-load-more-btn"
          :disabled="detail?.loadingMore"
          @click="loadMoreEvents(loopId, agentSpanId)"
        >
          {{ detail?.loadingMore ? 'Loading more events…' : 'Load more events' }}
        </button>
        <span v-if="detail?.moreError" class="event-load-more-error">{{ detail.moreError }}</span>
      </div>

      <div v-if="!eventItems.length && loadState === 'loaded'" class="detail-state">
        <p>No recorded events in this step.</p>
      </div>
    </template>
  </div>
</template>

<style scoped>
.exec-detail { display: flex; flex-direction: column; gap: 18px; padding: 18px; min-height: 160px; }
.detail-state { min-height: 160px; display: grid; place-content: center; justify-items: center; gap: 8px; color: var(--text-tertiary); font-size: 12px; text-align: center; }
.detail-state p { max-width: 360px; margin: 0; line-height: 1.6; }
.detail-state--error, .inline-state--error { color: var(--color-error, #ef4444); }
.detail-error-msg { color: var(--text-tertiary); font-size: 11px; }
.detail-spinner { width: 16px; height: 16px; border: 1.5px solid var(--border); border-top-color: var(--text-secondary); border-radius: 50%; animation: detail-spin 700ms linear infinite; }
.step-overview { display: flex; align-items: center; justify-content: space-between; gap: 24px; padding: 18px; border: 1px solid var(--border-subtle); border-radius: 12px; background: var(--bg-primary); box-shadow: 0 1px 2px rgba(0, 0, 0, .04); }
.step-overview-main { min-width: 0; display: flex; align-items: center; gap: 14px; }
.step-index { width: 40px; height: 40px; display: grid; place-items: center; flex: 0 0 auto; border-radius: 50%; background: var(--text-primary); color: var(--bg-primary); font-family: var(--font-mono); font-size: 14px; font-weight: 700; }
.step-kicker { margin-bottom: 3px; color: var(--text-tertiary); font-family: var(--font-mono); font-size: 9px; font-weight: 600; letter-spacing: .1em; text-transform: uppercase; }
.step-title { margin: 0; overflow: hidden; color: var(--text-primary); font-size: 15px; font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }
.step-subtitle { display: flex; gap: 10px; margin: 5px 0 0; color: var(--text-tertiary); font-family: var(--font-mono); font-size: 10px; }
.step-subtitle span + span::before { content: '·'; margin-right: 10px; }
.step-stats { display: grid; grid-template-columns: repeat(4, minmax(54px, auto)); gap: 4px; margin: 0; }
.step-stats div { padding: 7px 10px; border-left: 1px solid var(--border-subtle); }
.step-stats dt { color: var(--text-tertiary); font-size: 9px; text-transform: uppercase; letter-spacing: .06em; }
.step-stats dd { margin: 3px 0 0; color: var(--text-primary); font-family: var(--font-mono); font-size: 12px; font-weight: 600; }
.detail-provenance { display: flex; align-items: center; gap: 7px; padding: 8px 11px; border: 1px solid color-mix(in srgb, var(--color-warning, #f59e0b) 35%, var(--border-subtle)); border-radius: 8px; background: color-mix(in srgb, var(--color-warning, #f59e0b) 6%, var(--bg-secondary)); color: var(--text-secondary); font-size: 11px; }
.execution-error { padding: 9px 12px; border-left: 2px solid var(--color-error, #ef4444); background: color-mix(in srgb, var(--color-error, #ef4444) 8%, var(--bg-secondary)); color: var(--color-error, #ef4444); font-size: 12px; line-height: 1.45; white-space: pre-wrap; overflow-wrap: anywhere; }
.provenance-tag, .more-badge { padding: 2px 6px; border-radius: 4px; background: var(--bg-tertiary); font-family: var(--font-mono); font-size: 9px; text-transform: uppercase; }
.event-list-heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 0 2px; }
.event-list-heading h4 { margin: 0; color: var(--text-primary); font-size: 13px; font-weight: 600; }
.event-list-heading p { margin: 3px 0 0; color: var(--text-tertiary); font-size: 11px; }
.recorded-event-list { display: grid; gap: 10px; margin: 0; padding: 0; list-style: none; }
.recorded-event-item { min-width: 0; }
.event-card { min-width: 0; overflow: hidden; border: 1px solid var(--border-subtle); border-radius: 10px; background: var(--bg-primary); transition: border-color 160ms ease, box-shadow 160ms ease; }
.event-card[open] { border-color: color-mix(in srgb, var(--text-secondary) 25%, var(--border-subtle)); box-shadow: 0 2px 8px rgba(0, 0, 0, .04); }
.event-summary { min-height: 52px; display: flex; align-items: center; gap: 10px; padding: 9px 12px; cursor: pointer; list-style: none; }
.event-summary::-webkit-details-marker { display: none; }
.event-summary:hover { background: var(--bg-hover); }
.event-summary:focus-visible { outline: 2px solid var(--text-accent); outline-offset: -2px; }
.event-icon { width: 28px; height: 28px; display: grid; place-items: center; flex: 0 0 auto; border: 1px solid var(--border-subtle); border-radius: 7px; color: var(--text-secondary); }
.event-icon svg { width: 14px; height: 14px; fill: none; stroke: currentColor; stroke-width: 1.4; stroke-linecap: round; stroke-linejoin: round; }
.event-heading { min-width: 0; display: grid; gap: 2px; }
.event-heading strong { overflow: hidden; color: var(--text-primary); font-family: var(--font-mono); font-size: 11px; font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }
.event-label { color: var(--text-tertiary); font-size: 9px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; }
.event-timing { margin-left: auto; display: flex; gap: 6px; color: var(--text-tertiary); font-family: var(--font-mono); font-size: 9px; white-space: nowrap; }
.event-timing span + span { padding-left: 6px; border-left: 1px solid var(--border-subtle); color: var(--text-secondary); }
.event-error-flag { padding: 2px 6px; border-radius: 4px; background: color-mix(in srgb, var(--color-error, #ef4444) 12%, transparent); color: var(--color-error, #ef4444); font-size: 9px; font-weight: 600; text-transform: uppercase; }
.event-error-flag.error-cat--permission_denied { background: color-mix(in srgb, #f59e0b 12%, transparent); color: #d97706; }
.event-error-flag.error-cat--timeout { background: color-mix(in srgb, #f97316 12%, transparent); color: #ea580c; }
.event-error-flag.error-cat--invalid_input { background: color-mix(in srgb, #eab308 12%, transparent); color: #ca8a04; }
.event-error-flag.error-cat--network_error { background: color-mix(in srgb, #8b5cf6 12%, transparent); color: #7c3aed; }
.event-retry-flag { padding: 2px 6px; border-radius: 4px; background: color-mix(in srgb, #f59e0b 12%, transparent); color: #d97706; font-size: 9px; font-weight: 600; text-transform: uppercase; }
.event-retried-flag { padding: 2px 6px; border-radius: 4px; background: color-mix(in srgb, var(--text-accent) 10%, transparent); color: var(--text-accent); font-size: 9px; font-weight: 600; }
.cache-hit-badge { margin-left: 4px; padding: 1px 5px; border-radius: 3px; background: color-mix(in srgb, var(--color-success, #22c55e) 12%, transparent); color: var(--color-success, #22c55e); font-size: 9px; font-weight: 600; }
.input-summary-bar { display: flex; flex-wrap: wrap; gap: 6px; padding: 10px 12px; border-bottom: 1px solid var(--border-subtle); background: color-mix(in srgb, var(--text-accent) 4%, var(--bg-secondary)); }
.summary-chip { padding: 3px 8px; border: 1px solid var(--border-subtle); border-radius: 5px; background: var(--bg-primary); color: var(--text-secondary); font-family: var(--font-mono); font-size: 10px; }
.summary-chip strong { color: var(--text-primary); font-weight: 650; }
.thinking-preview { display: block; margin-top: 2px; color: var(--text-tertiary); font-size: 10px; font-weight: 400; line-height: 1.4; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 400px; }
.thinking-keywords { display: inline-flex; gap: 3px; margin-left: 4px; }
.keyword-tag { padding: 1px 5px; border-radius: 3px; background: color-mix(in srgb, var(--color-warning, #f59e0b) 15%, transparent); color: var(--color-warning, #d97706); font-size: 8px; font-weight: 600; text-transform: uppercase; }
.recorded-event-item--thinking .event-card { border-left: 2px dashed var(--color-warning, #f59e0b); background: color-mix(in srgb, var(--color-warning, #f59e0b) 3%, var(--bg-primary)); }
.recorded-event-item--thinking .event-icon { color: var(--color-warning, #d97706); border-color: color-mix(in srgb, var(--color-warning) 35%, var(--border-subtle)); }
.summary-chevron { flex: 0 0 auto; color: var(--text-tertiary); transition: transform 160ms ease; }
.event-card[open] .summary-chevron { transform: rotate(180deg); }
.event-body { display: grid; gap: 10px; padding: 12px; border-top: 1px solid var(--border-subtle); background: color-mix(in srgb, var(--bg-secondary) 45%, var(--bg-primary)); }
.event-body--split { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.event-no-content { padding: 18px; color: var(--text-tertiary); font-size: 11px; text-align: center; }
.event-load-more { display: flex; align-items: center; justify-content: center; flex-wrap: wrap; gap: 8px; }
.event-load-more-btn { min-height: 36px; padding: 8px 14px; border: 1px solid var(--border-subtle); border-radius: 8px; background: var(--bg-primary); color: var(--text-secondary); font-size: 11px; font-weight: 600; cursor: pointer; transition: border-color 150ms ease, color 150ms ease, background 150ms ease; }
.event-load-more-btn:hover:not(:disabled) { border-color: var(--text-accent); background: var(--bg-hover); color: var(--text-primary); }
.event-load-more-btn:focus-visible { outline: 2px solid var(--text-accent); outline-offset: 2px; }
.event-load-more-btn:disabled { cursor: wait; opacity: .68; }
.event-load-more-error { color: var(--color-error, #ef4444); font-size: 11px; }
.subagent-actions { padding: 0 12px 12px; background: color-mix(in srgb, var(--bg-secondary) 45%, var(--bg-primary)); }
.inline-expand-btn { min-height: 36px; padding: 7px 10px; border: 1px solid var(--border-subtle); border-radius: 7px; background: var(--bg-primary); color: var(--text-secondary); font-size: 11px; font-weight: 500; cursor: pointer; }
.inline-expand-btn:hover { border-color: var(--text-accent); color: var(--text-accent); }
.inline-expand-btn:focus-visible { outline: 2px solid var(--text-accent); outline-offset: 2px; }
.inline-subagent-section { margin-top: 10px; }
.inline-state { padding: 12px; color: var(--text-tertiary); font-size: 11px; }
.inline-unavailable { display: inline-flex; align-items: center; min-height: 36px; color: var(--text-tertiary); font-size: 11px; }
@keyframes detail-spin { to { transform: rotate(360deg); } }
@media (max-width: 1180px) { .step-overview { align-items: flex-start; flex-direction: column; } .step-stats { width: 100%; } .step-stats div:first-child { border-left: 0; } .event-body--split { grid-template-columns: 1fr; } }
@media (max-width: 640px) { .exec-detail { padding: 12px; } .step-overview { padding: 14px; } .step-stats { grid-template-columns: repeat(2, 1fr); } .step-stats div:nth-child(3) { border-left: 0; } .event-timing { display: none; } }
@media (prefers-reduced-motion: reduce) { .detail-spinner { animation: none; } .summary-chevron, .event-card { transition: none; } }
</style>
