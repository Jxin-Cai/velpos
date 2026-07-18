<script setup>
import { computed } from 'vue'

const props = defineProps({
  node: { type: Object, required: true },
  nodeType: { type: String, required: true }, // 'task' | 'loop' | 'subagent' | 'event'
  depth: { type: Number, default: 0 },
  expanded: { type: Boolean, default: false },
  loadState: { type: String, default: 'idle' },
  children: { type: Array, default: () => [] },
})

const emit = defineEmits(['toggle', 'select-loop'])

const canExpand = computed(() => {
  if (props.nodeType === 'task') return Boolean(props.node.loops?.length)
  if (props.nodeType === 'loop') return true
  if (props.nodeType === 'subagent') return props.node.is_expandable !== false
  return false
})

const icon = computed(() => {
  const map = {
    task: 'task',
    loop: 'loop',
    subagent: 'subagent',
    event: 'event',
  }
  return map[props.nodeType] || 'event'
})

const typeLabel = computed(() => {
  const map = {
    task: 'Task',
    loop: 'Loop',
    subagent: 'Agent',
    event: 'Event',
  }
  return map[props.nodeType] || 'Event'
})

const displayName = computed(() => {
  if (props.nodeType === 'task') return props.node.subject || 'Untitled task'
  if (props.nodeType === 'loop') {
    const model = props.node.model ? props.node.model.replace(/^claude-/, '') : ''
    return model || `Loop ${props.node.id?.slice(-6) || ''}`
  }
  if (props.nodeType === 'subagent') return props.node.subagent || 'Subagent'
  return props.node.type || 'Event'
})

const statusLabel = computed(() => {
  if (props.nodeType === 'task') return props.node.status || ''
  if (props.nodeType === 'loop') return props.node.stop_reason || ''
  return ''
})

const statusClass = computed(() => {
  const s = props.node.status || ''
  if (s === 'completed' || s === 'end_turn') return 'status-completed'
  if (s === 'in_progress' || s === 'running') return 'status-running'
  if (s === 'failed' || s === 'error') return 'status-failed'
  if (s === 'pending') return 'status-pending'
  return ''
})

const meta = computed(() => {
  const parts = []
  if (props.nodeType === 'task') {
    const loopCount = props.node.loops?.length || 0
    if (loopCount > 0) parts.push(`${loopCount} loop${loopCount > 1 ? 's' : ''}`)
  }
  if (props.nodeType === 'loop') {
    const usage = props.node.usage || {}
    const events = props.node.event_count || 0
    if (events > 0) parts.push(`${events} events`)
    const tokens = (usage.input_tokens || 0) + (usage.output_tokens || 0)
    if (tokens > 0) parts.push(`${formatTokens(tokens)} tok`)
  }
  return parts.join(' · ')
})

function formatTokens(n) {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`
  return String(n)
}

function handleClick() {
  if (props.nodeType === 'loop') {
    emit('select-loop', props.node.id)
  }
  if (canExpand.value) {
    emit('toggle', props.node.id || props.node.tool_use_id)
  }
}
</script>

<template>
  <div class="exec-row" :style="{ '--exec-depth': depth }">
    <button
      type="button"
      class="exec-header"
      :class="{ 'is-expanded': expanded, 'is-loading': loadState === 'loading' }"
      :aria-expanded="canExpand ? expanded : undefined"
      :disabled="!canExpand && nodeType !== 'loop'"
      @click="handleClick"
    >
      <span class="exec-expand" :class="{ rotated: expanded, invisible: !canExpand }" aria-hidden="true">
        <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="m6 4 4 4-4 4" />
        </svg>
      </span>
      <span class="exec-icon" :class="`exec-icon--${icon}`" aria-hidden="true">
        <svg v-if="icon === 'task'" viewBox="0 0 16 16"><path d="M3 3h10v10H3z" /><path d="M6 8l1.5 1.5L10 6" /></svg>
        <svg v-else-if="icon === 'loop'" viewBox="0 0 16 16"><path d="M8 3a5 5 0 1 1-4.33 2.5" /><path d="M3.67 2v3.5h3.5" /></svg>
        <svg v-else-if="icon === 'subagent'" viewBox="0 0 16 16"><rect x="3" y="4" width="10" height="8" rx="2"/><path d="M8 2v2M6 8h.01M10 8h.01"/></svg>
        <svg v-else viewBox="0 0 16 16"><circle cx="8" cy="8" r="3"/></svg>
      </span>
      <span class="exec-type">{{ typeLabel }}</span>
      <span class="exec-name">{{ displayName }}</span>
      <span v-if="meta" class="exec-meta">{{ meta }}</span>
      <span v-if="loadState === 'loading'" class="exec-spinner" aria-hidden="true"></span>
      <span v-if="statusLabel" class="exec-status" :class="statusClass">{{ statusLabel }}</span>
    </button>

    <div v-if="expanded && children.length" class="exec-children">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.exec-row { position: relative; }
.exec-row:not(:first-child)::before {
  content: '';
  position: absolute;
  top: -1px;
  left: calc(20px + var(--exec-depth, 0) * 18px);
  right: 0;
  height: 1px;
  background: var(--border-subtle);
  opacity: 0.5;
}
.exec-header {
  position: relative;
  width: 100%;
  min-height: 38px;
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 5px 10px 5px calc(8px + var(--exec-depth, 0) * 18px);
  border: 1px solid transparent;
  border-radius: 7px;
  background: transparent;
  color: inherit;
  cursor: pointer;
  text-align: left;
  font-size: 12px;
  transition: background 140ms ease, border-color 140ms ease;
}
.exec-header:hover { background: var(--bg-hover); }
.exec-header.is-expanded { background: color-mix(in srgb, var(--bg-secondary) 60%, transparent); }
.exec-header:disabled { cursor: default; }
.exec-header:disabled:hover { background: transparent; }
.exec-header:focus-visible { outline: 2px solid var(--text-accent); outline-offset: 1px; }
.exec-expand { width: 12px; height: 12px; display: grid; place-items: center; flex-shrink: 0; color: var(--text-tertiary); transition: transform 140ms ease; }
.exec-expand.rotated { transform: rotate(90deg); }
.exec-expand.invisible { visibility: hidden; }
.exec-icon { width: 20px; height: 20px; display: grid; place-items: center; flex-shrink: 0; border: 1px solid var(--border-subtle); border-radius: 5px; background: var(--bg-primary); color: var(--text-secondary); }
.exec-icon svg { width: 12px; height: 12px; fill: none; stroke: currentColor; stroke-width: 1.4; stroke-linecap: round; stroke-linejoin: round; }
.exec-icon--subagent { color: var(--text-accent); }
.exec-icon--task { color: var(--text-secondary); }
.exec-type { flex-shrink: 0; min-width: 36px; color: var(--text-tertiary); font-family: var(--font-mono); font-size: 9px; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; }
.exec-name { flex: 1; min-width: 0; overflow: hidden; color: var(--text-primary); font-weight: 500; text-overflow: ellipsis; white-space: nowrap; }
.exec-meta { flex-shrink: 0; color: var(--text-tertiary); font-family: var(--font-mono); font-size: 10px; }
.exec-spinner { width: 12px; height: 12px; flex-shrink: 0; border: 1.5px solid var(--border); border-top-color: var(--text-secondary); border-radius: 50%; animation: exec-spin 700ms linear infinite; }
.exec-status { flex-shrink: 0; padding: 1px 6px; border-radius: 4px; font-size: 10px; font-weight: 500; background: var(--bg-secondary); color: var(--text-tertiary); }
.exec-status.status-completed { color: var(--color-success, #22c55e); }
.exec-status.status-running { color: var(--text-accent); }
.exec-status.status-failed { color: var(--color-error, #ef4444); }
.exec-status.status-pending { color: var(--text-tertiary); }
.exec-children { margin-top: 1px; }
@keyframes exec-spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .exec-expand { transition: none; } .exec-spinner { animation: none; } }
@media (max-width: 640px) {
  .exec-header { gap: 5px; padding-right: 6px; }
  .exec-meta { display: none; }
}
</style>
