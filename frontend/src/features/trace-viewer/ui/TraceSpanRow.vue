<script setup>
import { computed, ref, watch } from 'vue'
import SpanPayloadViewer from './SpanPayloadViewer.vue'

const props = defineProps({
  node: { type: Object, required: true },
  depth: { type: Number, default: 0 },
})

const CONTAINER_TYPES = new Set(['run', 'agent', 'subagent', 'llm_turn'])
const expanded = ref(Boolean(props.node.children?.length && CONTAINER_TYPES.has(props.node.span_type)))
const manuallyToggled = ref(false)

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
  || props.node.input_preview
  || props.node.output_preview
  || thinkingPreview.value
  || hasMetadata.value,
))

const typeLabel = computed(() => {
  if (props.node.span_type === 'llm_turn') return `Turn ${String(props.node.turn_index || 1).padStart(2, '0')}`
  return ({
    run: 'Run',
    agent: 'Main',
    tool_call: 'Tool',
    subagent: 'Subagent',
  })[props.node.span_type] || 'Event'
})

const displayName = computed(() => {
  if (props.node.span_type === 'run') return 'Execution flow'
  if (props.node.span_type === 'llm_turn') {
    return firstMeaningfulLine(props.node.output_preview)
      || (thinkingPreview.value ? 'Thinking' : 'Assistant response')
  }
  if (props.node.span_type === 'subagent') return props.node.name || 'Subagent call'
  return props.node.name
})

const toolSummary = computed(() => {
  if (props.node.span_type !== 'tool_call' || !props.node.input_preview) return ''
  try {
    const value = JSON.parse(props.node.input_preview)
    const summary = value.command || value.file_path || value.path || value.query || value.pattern || value.url
    return typeof summary === 'string' ? summary.replace(/\s+/g, ' ').slice(0, 120) : ''
  } catch {
    return firstMeaningfulLine(props.node.input_preview).slice(0, 120)
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

watch(() => props.node.children?.length || 0, (count) => {
  if (count > 0 && !manuallyToggled.value && CONTAINER_TYPES.has(props.node.span_type)) {
    expanded.value = true
  }
})

function firstMeaningfulLine(value) {
  return String(value || '').split('\n').map(line => line.trim()).find(Boolean) || ''
}

function toggleExpanded() {
  if (!canExpand.value) return
  manuallyToggled.value = true
  expanded.value = !expanded.value
}

function formatDuration(ms) {
  if (!ms || ms <= 0) return ''
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(ms < 10000 ? 1 : 0)}s`
}
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
      <span v-if="node.agent_id && !['main', 'agent'].includes(node.agent_id)" class="span-agent">{{ node.agent_id.slice(0, 8) }}</span>
      <span v-if="node.duration_ms" class="span-duration">{{ formatDuration(node.duration_ms) }}</span>
      <span class="span-status" :class="`status-${node.status}`" :title="statusLabel">
        <span class="status-dot" aria-hidden="true"></span>
        <span class="status-text">{{ statusLabel }}</span>
      </span>
    </button>

    <div v-if="expanded" class="span-detail">
      <div v-if="node.input_preview || node.output_preview || thinkingPreview || hasMetadata" class="detail-card" :class="{ 'detail-card--tool': node.span_type === 'tool_call', 'detail-card--subagent': node.span_type === 'subagent' }">
        <div class="payload-grid" :class="{ 'payload-grid--split': node.input_preview && node.output_preview }">
          <SpanPayloadViewer :payload="node.input_preview" :label="node.span_type === 'tool_call' ? 'Request' : node.span_type === 'subagent' ? 'Invocation' : 'Input'" />
          <SpanPayloadViewer :payload="node.output_preview" :label="node.span_type === 'llm_turn' ? 'Assistant output' : node.span_type === 'subagent' ? 'Subagent return' : 'Response'" />
        </div>
        <SpanPayloadViewer v-if="thinkingPreview" :payload="thinkingPreview" label="Thinking" />
        <details v-if="hasMetadata" class="span-meta">
          <summary>Diagnostics</summary>
          <pre class="meta-content">{{ JSON.stringify(visibleMetadata, null, 2) }}</pre>
        </details>
      </div>

      <div v-if="node.children?.length" class="span-children">
        <div v-if="node.span_type === 'subagent'" class="children-caption">Internal timeline</div>
        <TraceSpanRow v-for="child in node.children" :key="child.id" :node="child" :depth="depth + 1" />
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
.span-duration, .span-agent { flex-shrink: 0; color: var(--text-tertiary); font-family: var(--font-mono); font-size: 10px; }
.span-agent { max-width: 78px; overflow: hidden; padding: 2px 5px; border-radius: 4px; background: var(--bg-tertiary); text-overflow: ellipsis; }
.span-status { min-width: 66px; display: inline-flex; align-items: center; gap: 6px; flex-shrink: 0; color: var(--text-tertiary); font-size: 10px; }
.status-dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.status-failed { color: var(--color-error, #ef4444); }
.status-denied, .status-cancelled { color: var(--color-warning, #f59e0b); }
.status-running { color: var(--text-accent); }
.status-running .status-dot { animation: trace-pulse 1.2s ease-in-out infinite; }
.span-detail { padding-left: calc(49px + var(--trace-depth) * 20px); }
.span-children { margin-top: 1px; }
.children-caption { padding: 7px 10px 3px 0; color: var(--text-tertiary); font-family: var(--font-mono); font-size: 9px; letter-spacing: .08em; text-transform: uppercase; }
.detail-card { margin: 7px 10px 9px 0; padding: 9px 10px; border: 1px solid var(--border-subtle); border-radius: 9px; background: color-mix(in srgb, var(--bg-secondary) 72%, transparent); }
.detail-card--subagent { border-color: color-mix(in srgb, var(--text-accent) 28%, var(--border-subtle)); background: color-mix(in srgb, var(--text-accent) 5%, var(--bg-secondary)); }
.payload-grid { display: grid; grid-template-columns: minmax(0, 1fr); gap: 8px; }
.payload-grid--split { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.span-meta { margin-top: 9px; border-top: 1px solid var(--border-subtle); padding-top: 7px; }
.span-meta summary { color: var(--text-tertiary); font-size: 10px; cursor: pointer; }
.meta-content { max-height: 180px; margin: 7px 0 0; overflow: auto; color: var(--text-secondary); font-family: var(--font-mono); font-size: 10px; line-height: 1.5; white-space: pre-wrap; }
@keyframes trace-pulse { 50% { opacity: .3; } }
@media (prefers-reduced-motion: reduce) { .span-expand, .span-header { transition: none; } .status-running .status-dot { animation: none; } }
@media (max-width: 700px) {
  .span-header { padding-right: 6px; gap: 6px; }
  .span-agent, .span-count, .span-summary { display: none; }
  .span-status { min-width: 8px; width: 8px; }
  .status-text { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0, 0, 0, 0); }
  .span-type { min-width: 35px; }
  .span-detail { padding-left: calc(37px + var(--trace-depth) * 14px); }
  .payload-grid--split { grid-template-columns: minmax(0, 1fr); }
}
</style>
