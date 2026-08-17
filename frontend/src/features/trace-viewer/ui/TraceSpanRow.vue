<script setup>
import { computed, ref } from 'vue'
import { formatDuration as _formatDuration } from '@shared/lib/formatTime'
import SpanPayloadViewer from './SpanPayloadViewer.vue'

const props = defineProps({
  node: { type: Object, required: true },
  depth: { type: Number, default: 0 },
  traceStartMs: { type: Number, default: 0 },
  traceDurationMs: { type: Number, default: 0 },
  durationThresholds: { type: Object, default: () => ({ p50: 0, p75: 0, p90: 0 }) },
})

const expanded = ref(false)

function capturedPayload(keys) {
  const sources = [props.node.metadata || {}, ...(props.node.metadata?.['otel.events'] || []).map(event => event?.attributes || {})]
  for (const source of sources) {
    for (const key of keys) {
      if (source?.[key] != null && source[key] !== '' && source[key] !== '<REDACTED>') return source[key]
    }
  }
  return null
}

const completeInput = computed(() => props.node.input_preview ?? capturedPayload([
  'user_prompt', 'prompt', 'request.model_input', 'tool_input', 'tool.input', 'tool_parameters', 'full_command', 'file_path', 'input',
]))
const completeOutput = computed(() => props.node.output_preview ?? capturedPayload([
  'response.model_output', 'tool_output', 'tool.output', 'tool.result', 'output',
]))

const visibleMetadata = computed(() => {
  const metadata = { ...(props.node.metadata || {}) }
  for (const key of ['role', 'inferred', 'tool_names', 'tool_use_ids', 'parent_tool_use_id', 'source', 'thinking_preview']) {
    delete metadata[key]
  }
  return metadata
})

const hasMetadata = computed(() => Object.keys(visibleMetadata.value).length > 0)
const thinkingPreview = computed(() => props.node.metadata?.thinking_preview || '')
const canExpand = computed(() => Boolean(
  props.node.children?.length
  || completeInput.value != null
  || completeOutput.value != null
  || thinkingPreview.value
  || hasMetadata.value,
))

const typeLabel = computed(() => {
  if (props.node.span_type === 'llm_turn') return props.node.metadata?.['otel.span_name'] ? 'LLM' : `Turn ${String(props.node.turn_index || 1).padStart(2, '0')}`
  return ({
    run: 'Run',
    agent: props.node.metadata?.['otel.span_name'] ? 'Turn' : 'Main',
    tool_call: 'Tool',
    subagent: 'Subagent',
    tool_execution: 'Exec',
    permission_wait: 'Wait',
    hook: 'Hook',
    otel_span: 'Span',
  })[props.node.span_type] || 'Event'
})

const displayName = computed(() => {
  if (props.node.span_type === 'run') return 'Execution flow'
  if (props.node.span_type === 'llm_turn') {
    if (props.node.metadata?.['otel.span_name']) {
      return props.node.metadata?.model || props.node.metadata?.['gen_ai.request.model'] || 'Model request'
    }
    return firstMeaningfulLine(props.node.output_preview)
      || (thinkingPreview.value ? 'Thinking' : 'Assistant response')
  }
  if (props.node.span_type === 'subagent') return props.node.name || 'Subagent call'
  if (props.node.span_type === 'agent' && props.node.metadata?.['otel.span_name']) return 'Agent interaction'
  if (props.node.span_type === 'tool_execution') return 'Tool execution'
  if (props.node.span_type === 'permission_wait') return 'Permission wait'
  if (props.node.span_type === 'hook') return props.node.metadata?.hook_name || 'Hook execution'
  return props.node.name
})

const toolSummary = computed(() => {
  if (props.node.span_type !== 'tool_call' || !completeInput.value) return ''
  try {
    const value = typeof completeInput.value === 'string' ? JSON.parse(completeInput.value) : completeInput.value
    const summary = value.command || value.file_path || value.path || value.query || value.pattern || value.url
    return typeof summary === 'string' ? summary.replace(/\s+/g, ' ').slice(0, 120) : ''
  } catch {
    return firstMeaningfulLine(completeInput.value).slice(0, 120)
  }
})

const statusLabel = computed(() => ({
  completed: 'Done',
  failed: 'Failed',
  denied: 'Denied',
  cancelled: 'Cancelled',
  abandoned: 'Abandoned',
  running: 'Running',
})[props.node.status] || props.node.status || 'Unknown')

const waterfallBar = computed(() => {
  if (!props.traceDurationMs) return null
  const start = Date.parse(props.node.started_time || '')
  if (!Number.isFinite(start)) return null
  const explicitEnd = Date.parse(props.node.ended_time || '')
  const end = Number.isFinite(explicitEnd)
    ? explicitEnd
    : start + Math.max(Number(props.node.duration_ms) || 0, 0)
  const left = Math.max(0, Math.min(((start - props.traceStartMs) / props.traceDurationMs) * 100, 100))
  const naturalWidth = Math.max(((Math.max(end, start) - start) / props.traceDurationMs) * 100, 0)
  const width = Math.max(0.7, Math.min(naturalWidth, 100 - left))
  return {
    left: `${left}%`,
    width: `${width}%`,
    labelLeft: `${Math.min(left + width + 0.8, 88)}%`,
  }
})

const latencyBand = computed(() => {
  // Structural containers describe the whole trace/session and are not actionable
  // latency samples. Giving them the hottest colour makes every trace look slow.
  if (['run', 'agent'].includes(props.node.span_type)) return 'container'
  const duration = Number(props.node.duration_ms) || 0
  if (!duration) return 'none'
  if (props.durationThresholds.p90 && duration >= props.durationThresholds.p90) return 'hot'
  if (props.durationThresholds.p75 && duration >= props.durationThresholds.p75) return 'high'
  if (props.durationThresholds.p50 && duration >= props.durationThresholds.p50) return 'medium'
  return 'low'
})

function firstMeaningfulLine(value) {
  return String(value || '').split('\n').map(line => line.trim()).find(Boolean) || ''
}

function toggleExpanded() {
  if (!canExpand.value) return
  expanded.value = !expanded.value
}

const formatDuration = (ms) => _formatDuration(ms, { zeroValue: '' })
</script>

<template>
  <div
    class="span-row"
    :class="[`span-row--${node.span_type}`, { 'span-row--root': depth === 0 }]"
    :style="{ '--trace-depth': depth }"
  >
    <button
      type="button"
      class="span-header"
      :class="{ 'is-expanded': expanded }"
      :aria-expanded="canExpand ? expanded : undefined"
      :disabled="!canExpand"
      @click="toggleExpanded"
    >
      <span class="span-expand" :class="{ rotated: expanded, invisible: !canExpand }" aria-hidden="true">
        <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="m6 4 4 4-4 4" />
        </svg>
      </span>
      <span class="span-icon" :class="`span-icon--${node.span_type}`" aria-hidden="true">
        <svg v-if="node.span_type === 'run'" viewBox="0 0 16 16"><circle cx="4" cy="3" r="1.5"/><circle cx="11.5" cy="8" r="1.5"/><circle cx="5.5" cy="13" r="1.5"/><path d="M4 4.5v5A3.5 3.5 0 0 0 5.5 13M5.5 3h1A5 5 0 0 1 11.5 8"/></svg>
        <svg v-else-if="node.span_type === 'llm_turn'" viewBox="0 0 16 16"><path d="M3 4.5A2.5 2.5 0 0 1 5.5 2h5A2.5 2.5 0 0 1 13 4.5v4a2.5 2.5 0 0 1-2.5 2.5H7l-3.5 2v-2.8A2.5 2.5 0 0 1 3 8.5z"/></svg>
        <svg v-else-if="node.span_type === 'tool_call'" viewBox="0 0 16 16"><path d="m3 13 4-4M9 3a3 3 0 0 0 4 4L9 11 5 7z"/></svg>
        <svg v-else-if="node.span_type === 'agent' || node.span_type === 'subagent'" viewBox="0 0 16 16"><rect x="3" y="4" width="10" height="8" rx="2"/><path d="M8 2v2M6 8h.01M10 8h.01"/></svg>
        <svg v-else viewBox="0 0 16 16"><circle cx="8" cy="8" r="3"/></svg>
      </span>
      <span class="span-type">{{ typeLabel }}</span>
      <span class="span-copy">
        <span class="span-name">{{ displayName }}</span>
        <span v-if="toolSummary" class="span-summary">{{ toolSummary }}</span>
      </span>
      <span v-if="node.tool_count && node.span_type !== 'tool_call'" class="span-count">
        {{ node.tool_count }} {{ node.tool_count === 1 ? 'tool' : 'tools' }}
      </span>
      <span v-if="node.metadata?.input_tokens" class="span-tokens" :title="`In: ${node.metadata.input_tokens} Out: ${node.metadata.output_tokens || 0}`">
        {{ Math.round((node.metadata.input_tokens + (node.metadata.output_tokens || 0)) / 1000) }}k tok
      </span>
      <span v-if="node.metadata?.ttft_ms" class="span-otel-attr" :title="`Time to first token: ${node.metadata.ttft_ms}ms`">TTFT {{ formatDuration(node.metadata.ttft_ms) }}</span>
      <span v-if="Number(node.metadata?.attempt) > 1" class="span-otel-attr span-otel-attr--warning">{{ node.metadata.attempt }} attempts</span>
      <span v-if="node.agent_id && !['main', 'agent'].includes(node.agent_id)" class="span-agent">{{ node.agent_id.slice(0, 8) }}</span>
      <span class="span-status" :class="`status-${node.status}`" :title="statusLabel">
        <span class="status-dot" aria-hidden="true"></span>
        <span class="status-text">{{ statusLabel }}</span>
      </span>
      <span v-if="latencyBand === 'hot'" class="span-latency-badge" :title="`Trace-local p90: ${formatDuration(durationThresholds.p90)}`">Top 10%</span>
      <span v-if="node.parallelGroup" class="span-parallel-badge" :title="`${node.parallelGroup.spanCount} overlapping spans · peak concurrency ${node.parallelGroup.peak}`">
        Parallel {{ node.parallelGroup.branchIndex }}/{{ node.parallelGroup.spanCount }}
      </span>
      <span v-if="waterfallBar" class="span-waterfall-track" :title="`${displayName} · ${formatDuration(node.duration_ms) || '0ms'} · ${latencyBand} latency`">
        <span class="span-waterfall-grid" aria-hidden="true"></span>
        <span class="span-waterfall-bar" :class="[`latency-${latencyBand}`, { 'has-error': ['failed', 'denied', 'abandoned'].includes(node.status) }]" :style="{ left: waterfallBar.left, width: waterfallBar.width }" aria-hidden="true"></span>
        <span v-if="node.duration_ms" class="span-waterfall-duration" :style="{ left: waterfallBar.labelLeft }">{{ formatDuration(node.duration_ms) }}</span>
      </span>
    </button>

    <div v-if="expanded" class="span-detail">
      <div v-if="completeInput != null || completeOutput != null || thinkingPreview || hasMetadata" class="detail-card" :class="{ 'detail-card--tool': node.span_type === 'tool_call', 'detail-card--subagent': node.span_type === 'subagent' }">
        <div class="payload-grid" :class="{ 'payload-grid--split': completeInput != null && completeOutput != null }">
          <SpanPayloadViewer :payload="completeInput" :label="node.span_type === 'tool_call' ? 'Complete request' : node.span_type === 'subagent' ? 'Complete invocation' : 'Complete input'" start-expanded />
          <SpanPayloadViewer :payload="completeOutput" :label="node.span_type === 'llm_turn' ? 'Complete assistant output' : node.span_type === 'subagent' ? 'Complete subagent return' : 'Complete response'" start-expanded />
        </div>
        <div v-if="completeInput == null || completeOutput == null" class="capture-coverage" role="note">
          <span>{{ completeInput == null ? 'Input not emitted by source' : 'Input captured' }}</span>
          <span>{{ completeOutput == null ? 'Output not emitted by source' : 'Output captured' }}</span>
        </div>
        <SpanPayloadViewer v-if="thinkingPreview" :payload="thinkingPreview" label="Thinking" start-expanded />
        <details v-if="hasMetadata" class="span-meta">
          <summary>Diagnostics</summary>
          <pre class="meta-content">{{ JSON.stringify(visibleMetadata, null, 2) }}</pre>
        </details>
      </div>

      <div v-if="node.children?.length" class="span-children">
        <div v-if="node.span_type === 'subagent'" class="children-caption">Nested spans</div>
        <template v-for="child in node.children" :key="child.id">
          <div v-if="child.parallelGroup?.first" class="parallel-boundary parallel-boundary--split">
            <i aria-hidden="true"></i>
            <span>Parallel split · {{ child.parallelGroup.spanCount }} overlapping spans · peak {{ child.parallelGroup.peak }} at once</span>
          </div>
          <TraceSpanRow :node="child" :depth="depth + 1" :trace-start-ms="traceStartMs" :trace-duration-ms="traceDurationMs" :duration-thresholds="durationThresholds" />
          <div v-if="child.parallelGroup?.last" class="parallel-boundary parallel-boundary--join">
            <i aria-hidden="true"></i>
            <span>Parallel join · execution continues after all branches finish</span>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.span-row { position: relative; }
.span-row:not(.span-row--root)::before {
  content: '';
  position: absolute;
  top: -2px;
  bottom: -2px;
  left: calc(20px + (var(--trace-depth) - 1) * 20px);
  width: 1px;
  background: var(--border-subtle);
}
.span-header {
  position: relative;
  width: 100%;
  min-height: 44px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px 6px calc(8px + var(--trace-depth) * 20px);
  border: 1px solid transparent;
  border-radius: 9px;
  background: transparent;
  color: inherit;
  cursor: pointer;
  text-align: left;
  transition: background 160ms ease, border-color 160ms ease;
}
.span-header:hover { background: var(--bg-hover); }
.span-header.is-expanded { background: color-mix(in srgb, var(--bg-secondary) 76%, transparent); }
.span-row--agent > .span-header, .span-row--subagent > .span-header {
  margin: 3px 0;
  border-color: var(--border-subtle);
  background: var(--bg-secondary);
}
.span-row--subagent > .span-header { border-color: color-mix(in srgb, var(--text-accent) 35%, var(--border-subtle)); }
.span-row--llm_turn > .span-header { border-bottom-color: color-mix(in srgb, var(--border-subtle) 62%, transparent); border-radius: 7px; }
.span-header:disabled { cursor: default; }
.span-header:disabled:hover { background: transparent; }
.span-header:focus-visible { outline: 2px solid var(--text-accent); outline-offset: 1px; }
.span-expand { width: 12px; height: 12px; display: grid; place-items: center; flex-shrink: 0; color: var(--text-tertiary); transition: transform 160ms ease; }
.span-expand.rotated { transform: rotate(90deg); }
.span-expand.invisible { visibility: hidden; }
.span-icon { width: 22px; height: 22px; display: grid; place-items: center; flex-shrink: 0; border: 1px solid var(--border-subtle); border-radius: 6px; background: var(--bg-primary); color: var(--text-secondary); }
.span-icon svg { width: 13px; height: 13px; fill: none; stroke: currentColor; stroke-width: 1.35; stroke-linecap: round; stroke-linejoin: round; }
.span-icon--agent, .span-icon--subagent { color: var(--text-accent); }
.span-type { flex-shrink: 0; min-width: 42px; color: var(--text-tertiary); font-family: var(--font-mono); font-size: 9px; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; }
.span-copy { min-width: 0; display: flex; flex: 1; align-items: baseline; gap: 8px; }
.span-name { min-width: 0; overflow: hidden; color: var(--text-primary); font-size: 12px; font-weight: 520; text-overflow: ellipsis; white-space: nowrap; }
.span-row--tool_call .span-name { flex-shrink: 0; }
.span-summary { min-width: 0; overflow: hidden; color: var(--text-tertiary); font-family: var(--font-mono); font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.span-count { flex-shrink: 0; padding: 2px 6px; border: 1px solid var(--border-subtle); border-radius: 999px; color: var(--text-tertiary); font-size: 9px; }
.span-tokens { flex-shrink: 0; padding: 2px 5px; color: var(--text-tertiary); font-family: var(--font-mono); font-size: 9px; opacity: 0.8; }
.span-otel-attr { flex-shrink: 0; padding: 2px 5px; border-radius: 4px; background: var(--bg-tertiary); color: var(--text-tertiary); font-family: var(--font-mono); font-size: 9px; }
.span-otel-attr--warning { color: var(--color-warning, #f59e0b); }
.span-agent { flex-shrink: 0; color: var(--text-tertiary); font-family: var(--font-mono); font-size: 10px; }
.span-agent { max-width: 78px; overflow: hidden; padding: 2px 5px; border-radius: 4px; background: var(--bg-tertiary); text-overflow: ellipsis; }
.span-latency-badge { flex: 0 0 auto; padding: 2px 5px; border-radius: 4px; background: color-mix(in srgb, #ef4444 13%, transparent); color: #dc2626; font-family: var(--font-mono); font-size: 8px; font-weight: 700; text-transform: uppercase; }
.span-parallel-badge { flex: 0 0 auto; padding: 2px 5px; border: 1px solid color-mix(in srgb, #8b5cf6 28%, transparent); border-radius: 4px; background: color-mix(in srgb, #8b5cf6 10%, transparent); color: #7c3aed; font-family: var(--font-mono); font-size: 8px; font-weight: 650; white-space: nowrap; }
.span-status { min-width: 66px; display: inline-flex; align-items: center; gap: 6px; flex-shrink: 0; color: var(--text-tertiary); font-size: 10px; }
.status-dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.status-failed { color: var(--color-error, #ef4444); }
.status-denied, .status-cancelled { color: var(--color-warning, #f59e0b); }
.status-running { color: var(--text-accent); }
.status-running .status-dot { animation: trace-pulse 1.2s ease-in-out infinite; }
.span-waterfall-track { position: relative; min-width: 220px; height: 28px; flex: 0 1 40%; overflow: hidden; border-left: 1px solid var(--border-subtle); background: color-mix(in srgb, var(--bg-secondary) 48%, transparent); }
.span-waterfall-grid { position: absolute; inset: 0; background-image: linear-gradient(to right, color-mix(in srgb, var(--border-subtle) 62%, transparent) 1px, transparent 1px); background-size: 25% 100%; }
.span-waterfall-bar { position: absolute; top: 7px; height: 14px; min-width: 2px; border-radius: 3px; opacity: .86; box-shadow: inset 0 0 0 1px rgba(15,23,42,.12); }
.span-waterfall-bar.latency-low { background: #38bdf8; }
.span-waterfall-bar.latency-medium { background: #818cf8; }
.span-waterfall-bar.latency-high { background: #f59e0b; }
.span-waterfall-bar.latency-hot { background: linear-gradient(90deg, #f97316, #ef4444); opacity: .96; }
.span-waterfall-bar.latency-container { background: color-mix(in srgb, var(--text-accent) 42%, var(--text-tertiary)); opacity: .38; }
.span-waterfall-bar.latency-none { background: var(--text-tertiary); opacity: .45; }
.span-waterfall-bar.has-error { outline: 1px solid var(--color-error, #ef4444); outline-offset: 1px; }
.span-waterfall-duration { position: absolute; z-index: 1; top: 7px; color: var(--text-secondary); font-family: var(--font-mono); font-size: 9px; font-weight: 600; line-height: 14px; white-space: nowrap; text-shadow: 0 1px 0 var(--bg-primary); }
.span-detail { padding-left: calc(49px + var(--trace-depth) * 20px); }
.span-children { margin-top: 1px; }
.parallel-boundary { position: relative; min-height: 24px; display: flex; align-items: center; gap: 7px; margin-left: calc(47px + var(--trace-depth) * 20px); color: #7c3aed; font-family: var(--font-mono); font-size: 8px; font-weight: 600; letter-spacing: .025em; text-transform: uppercase; }
.parallel-boundary i { width: 18px; height: 10px; flex: 0 0 auto; border-left: 2px solid currentColor; border-right: 2px solid currentColor; }
.parallel-boundary--split i { border-top: 2px solid currentColor; border-radius: 4px 4px 0 0; }
.parallel-boundary--join i { border-bottom: 2px solid currentColor; border-radius: 0 0 4px 4px; }
.children-caption { padding: 7px 10px 3px 0; color: var(--text-tertiary); font-family: var(--font-mono); font-size: 9px; letter-spacing: .08em; text-transform: uppercase; }
.detail-card { margin: 7px 10px 9px 0; padding: 9px 10px; border: 1px solid var(--border-subtle); border-radius: 9px; background: color-mix(in srgb, var(--bg-secondary) 72%, transparent); }
.detail-card--subagent { border-color: color-mix(in srgb, var(--text-accent) 28%, var(--border-subtle)); background: color-mix(in srgb, var(--text-accent) 5%, var(--bg-secondary)); }
.capture-coverage { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; color: var(--text-tertiary); font-size: 9px; }
.capture-coverage span { padding: 3px 6px; border: 1px solid var(--border-subtle); border-radius: 4px; background: var(--bg-primary); }
.payload-grid { display: grid; grid-template-columns: minmax(0, 1fr); gap: 8px; }
.payload-grid--split { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.span-meta { margin-top: 9px; border-top: 1px solid var(--border-subtle); padding-top: 7px; }
.span-meta summary { color: var(--text-tertiary); font-size: 10px; cursor: pointer; }
.meta-content { max-height: 180px; margin: 7px 0 0; overflow: auto; color: var(--text-secondary); font-family: var(--font-mono); font-size: 10px; line-height: 1.5; white-space: pre-wrap; }
@keyframes trace-pulse { 50% { opacity: .3; } }
@media (prefers-reduced-motion: reduce) { .span-expand, .span-header { transition: none; } .status-running .status-dot { animation: none; } }
@media (max-width: 700px) {
  .span-header { padding-right: 6px; gap: 6px; }
  .span-agent, .span-count, .span-summary, .span-otel-attr, .span-tokens { display: none; }
  .span-status { min-width: 8px; width: 8px; }
  .status-text { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0, 0, 0, 0); }
  .span-type { min-width: 35px; }
  .span-detail { padding-left: calc(37px + var(--trace-depth) * 14px); }
  .span-waterfall-track { min-width: 150px; flex-basis: 42%; }
  .payload-grid--split { grid-template-columns: minmax(0, 1fr); }
}
</style>
