<script setup>
import { computed, ref, watch } from 'vue'
import SpanPayloadViewer from './SpanPayloadViewer.vue'

const props = defineProps({
  node: { type: Object, required: true },
  depth: { type: Number, default: 0 },
})

const expanded = ref(Boolean(props.node.children?.length))
const manuallyToggled = ref(false)
const canExpand = computed(() => Boolean(
  props.node.children?.length
  || props.node.input_preview
  || props.node.output_preview
  || (props.node.metadata && Object.keys(props.node.metadata).length),
))

const typeLabel = computed(() => ({
  run: 'Run',
  llm_turn: 'Turn',
  tool_call: 'Tool',
  subagent: 'Agent',
}[props.node.span_type] || 'Event'))

const statusLabel = computed(() => ({
  completed: 'Done',
  failed: 'Failed',
  denied: 'Denied',
  cancelled: 'Cancelled',
  running: 'Running',
}[props.node.status] || props.node.status || 'Unknown'))

watch(() => props.node.children?.length || 0, (count) => {
  if (count > 0 && !manuallyToggled.value) expanded.value = true
})

function toggleExpanded() {
  if (!canExpand.value) return
  manuallyToggled.value = true
  expanded.value = !expanded.value
}

function formatDuration(ms) {
  if (!ms || ms <= 0) return ''
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}
</script>

<template>
  <div class="span-row" :class="{ 'span-row--root': depth === 0 }" :style="{ '--trace-depth': depth }">
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
        <svg v-else-if="node.span_type === 'subagent'" viewBox="0 0 16 16"><rect x="3" y="4" width="10" height="8" rx="2"/><path d="M8 2v2M6 8h.01M10 8h.01"/></svg>
        <svg v-else viewBox="0 0 16 16"><circle cx="8" cy="8" r="3"/></svg>
      </span>
      <span class="span-type">{{ typeLabel }}</span>
      <span class="span-name">{{ node.name }}</span>
      <span v-if="node.agent_id" class="span-agent">{{ node.agent_id.slice(0, 8) }}</span>
      <span v-if="node.duration_ms" class="span-duration">{{ formatDuration(node.duration_ms) }}</span>
      <span class="span-status" :class="`status-${node.status}`">
        <span class="status-dot" aria-hidden="true"></span>
        {{ statusLabel }}
      </span>
    </button>

    <div v-if="expanded" class="span-detail">
      <div v-if="node.input_preview || node.output_preview || (node.metadata && Object.keys(node.metadata).length)" class="detail-card">
        <SpanPayloadViewer :payload="node.input_preview" label="Input" />
        <SpanPayloadViewer :payload="node.output_preview" label="Output" />
        <div v-if="node.metadata && Object.keys(node.metadata).length" class="span-meta">
          <div class="payload-label">Metadata</div>
          <pre class="meta-content">{{ JSON.stringify(node.metadata, null, 2) }}</pre>
        </div>
      </div>

      <div v-if="node.children?.length" class="span-children">
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
  top: -1px;
  bottom: -1px;
  left: calc(19px + (var(--trace-depth) - 1) * 18px);
  width: 1px;
  background: var(--border-subtle);
}
.span-header {
  position: relative;
  width: 100%;
  min-height: 38px;
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 5px 10px 5px calc(8px + var(--trace-depth) * 18px);
  border: 1px solid transparent;
  border-radius: 9px;
  background: transparent;
  color: inherit;
  cursor: pointer;
  text-align: left;
  transition: background 150ms ease, border-color 150ms ease;
}
.span-header:hover { background: var(--bg-hover); }
.span-header.is-expanded { border-color: color-mix(in srgb, var(--border-subtle) 72%, transparent); background: var(--bg-secondary); }
.span-header:disabled { cursor: default; }
.span-header:disabled:hover { background: transparent; }
.span-header:focus-visible { outline: 2px solid var(--text-accent); outline-offset: 1px; }
.span-expand {
  width: 12px;
  height: 12px;
  display: grid;
  place-items: center;
  flex-shrink: 0;
  color: var(--text-tertiary);
  transition: transform 150ms ease;
}
.span-expand.rotated { transform: rotate(90deg); }
.span-expand.invisible { visibility: hidden; }
.span-icon {
  width: 20px;
  height: 20px;
  display: grid;
  place-items: center;
  flex-shrink: 0;
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  background: var(--bg-primary);
  color: var(--text-secondary);
}
.span-icon svg { width: 13px; height: 13px; fill: none; stroke: currentColor; stroke-width: 1.35; stroke-linecap: round; stroke-linejoin: round; }
.span-icon--subagent { color: var(--text-accent); }
.span-type {
  flex-shrink: 0;
  width: 38px;
  color: var(--text-tertiary);
  font-family: var(--font-mono);
  font-size: 9px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.span-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  color: var(--text-primary);
  font-size: 12px;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.span-duration, .span-agent { flex-shrink: 0; color: var(--text-tertiary); font-family: var(--font-mono); font-size: 10px; }
.span-agent { max-width: 78px; overflow: hidden; padding: 2px 5px; border-radius: 4px; background: var(--bg-tertiary); text-overflow: ellipsis; }
.span-status {
  min-width: 68px;
  display: inline-flex;
  align-items: center;
  justify-content: flex-start;
  gap: 6px;
  flex-shrink: 0;
  color: var(--text-tertiary);
  font-size: 10px;
}
.status-dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.status-completed { color: var(--text-tertiary); }
.status-failed { color: var(--color-error, #ef4444); }
.status-denied, .status-cancelled { color: var(--color-warning, #f59e0b); }
.status-running { color: var(--text-accent); }
.status-running .status-dot { animation: trace-pulse 1.2s ease-in-out infinite; }
.span-detail { padding-left: calc(47px + var(--trace-depth) * 18px); }
.detail-card {
  margin: 4px 10px 8px 0;
  padding: 8px 10px;
  border: 1px solid var(--border-subtle);
  border-radius: 9px;
  background: color-mix(in srgb, var(--bg-secondary) 70%, transparent);
}
.span-meta { margin-top: 8px; }
.payload-label { margin-bottom: 4px; color: var(--text-tertiary); font-size: 9px; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; }
.meta-content {
  max-height: 180px;
  margin: 0;
  overflow: auto;
  color: var(--text-secondary);
  font-family: var(--font-mono);
  font-size: 10px;
  line-height: 1.5;
  white-space: pre-wrap;
}
.span-children { margin-top: 2px; }
@keyframes trace-pulse { 50% { opacity: .3; } }
@media (prefers-reduced-motion: reduce) {
  .span-expand, .span-header { transition: none; }
  .status-running .status-dot { animation: none; }
}
@media (max-width: 640px) {
  .span-header { padding-right: 6px; }
  .span-agent { display: none; }
  .span-status { min-width: 8px; width: 8px; overflow: hidden; gap: 10px; }
  .span-duration { font-size: 9px; }
  .span-type { width: 32px; }
  .span-detail { padding-left: calc(34px + var(--trace-depth) * 14px); }
}
</style>
