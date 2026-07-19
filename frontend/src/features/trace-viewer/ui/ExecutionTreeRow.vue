<script setup>
import { computed, useSlots } from 'vue'

const slots = useSlots()

const props = defineProps({
  node: { type: Object, required: true },
  nodeType: { type: String, required: true }, // 'task' | 'loop' | 'subagent' | 'event'
  depth: { type: Number, default: 0 },
  expanded: { type: Boolean, default: false },
  selected: { type: Boolean, default: false },
  loadState: { type: String, default: 'idle' },
})

const emit = defineEmits(['toggle', 'select-loop'])

const canExpand = computed(() => {
  if (props.nodeType === 'task') return Boolean(props.node.loops?.length)
  if (props.nodeType === 'loop') return true
  if (props.nodeType === 'subagent') return Boolean(props.node.span_id) || props.node.is_expandable !== false
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
    loop: 'Step',
    subagent: 'Agent',
    event: 'Event',
  }
  if (props.nodeType === 'loop' && props.node.sequence) return `Step ${props.node.sequence}`
  return map[props.nodeType] || 'Event'
})

const displayName = computed(() => {
  if (props.nodeType === 'task') return props.node.subject || 'Untitled task'
  if (props.nodeType === 'loop') {
    const tools = props.node.tool_names || []
    if (tools.length > 0) {
      const visibleTools = tools.slice(0, 2).join(' + ')
      return tools.length > 2 ? `${visibleTools} +${tools.length - 2}` : visibleTools
    }
    const model = props.node.model ? props.node.model.replace(/^claude-/, '') : ''
    return model ? `${model} response` : 'Model response'
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
    if (loopCount > 0) parts.push(`${loopCount} step${loopCount > 1 ? 's' : ''}`)
  }
  if (props.nodeType === 'loop') {
    const usage = props.node.usage || {}
    const events = props.node.event_count || 0
    if (props.node.duration_ms > 0) parts.push(formatDuration(props.node.duration_ms))
    if (events > 0) parts.push(`${events} events`)
    const tokens = (usage.input_tokens || 0) + (usage.output_tokens || 0)
    if (tokens > 0) parts.push(`${formatTokens(tokens)} tok`)
    const subagentCount = props.node.subagent_count || 0
    if (subagentCount > 0) parts.push(`${subagentCount} subagent${subagentCount > 1 ? 's' : ''}`)
  }
  return parts.join(' · ')
})

const supportingText = computed(() => {
  if (props.nodeType === 'task') return props.node.description || ''
  if (props.nodeType === 'loop') {
    const time = formatClockTime(props.node.started_time)
    const model = props.node.model ? props.node.model.replace(/^claude-/, '') : ''
    return [time, model].filter(Boolean).join(' · ')
  }
  return ''
})

function formatTokens(n) {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`
  return String(n)
}

function formatDuration(ms) {
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(ms < 10000 ? 1 : 0)}s`
  const minutes = Math.floor(ms / 60000)
  const seconds = Math.round((ms % 60000) / 1000)
  return `${minutes}m ${seconds}s`
}

function formatClockTime(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return new Intl.DateTimeFormat(undefined, {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(date)
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
    <div
      type="button"
      class="exec-header"
      :class="{ 'is-expanded': expanded, 'is-selected': selected, 'is-loading': loadState === 'loading' }"
      :aria-expanded="canExpand ? expanded : undefined"
      :aria-current="selected ? 'step' : undefined"
      :aria-disabled="!canExpand && nodeType !== 'loop'"
      :tabindex="!canExpand && nodeType !== 'loop' ? -1 : 0"
      role="button"
      @click="handleClick"
      @keydown.enter.space.prevent="handleClick"
    >
      <span class="exec-expand" :class="{ rotated: expanded, invisible: !canExpand }" aria-hidden="true">
        <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="m6 4 4 4-4 4" />
        </svg>
      </span>
      <span v-if="nodeType === 'loop'" class="exec-step-number" aria-hidden="true">{{ node.sequence || '·' }}</span>
      <span v-else class="exec-icon" :class="`exec-icon--${icon}`" aria-hidden="true">
        <svg v-if="icon === 'task'" viewBox="0 0 16 16"><path d="M3 3h10v10H3z" /><path d="M6 8l1.5 1.5L10 6" /></svg>
        <svg v-else-if="icon === 'loop'" viewBox="0 0 16 16"><path d="M8 3a5 5 0 1 1-4.33 2.5" /><path d="M3.67 2v3.5h3.5" /></svg>
        <svg v-else-if="icon === 'subagent'" viewBox="0 0 16 16"><rect x="3" y="4" width="10" height="8" rx="2"/><path d="M8 2v2M6 8h.01M10 8h.01"/></svg>
        <svg v-else viewBox="0 0 16 16"><circle cx="8" cy="8" r="3"/></svg>
      </span>
      <span class="exec-content">
        <span class="exec-title-line">
          <span class="exec-type">{{ typeLabel }}</span>
          <span class="exec-name">{{ displayName }}</span>
        </span>
        <span v-if="supportingText || meta" class="exec-support-line">
          <span v-if="supportingText" class="exec-support">{{ supportingText }}</span>
          <span v-if="meta" class="exec-meta">{{ meta }}</span>
        </span>
      </span>
      <span v-if="loadState === 'loading'" class="exec-spinner" aria-hidden="true"></span>
      <span v-if="statusLabel" class="exec-status" :class="statusClass">{{ statusLabel }}</span>
      <button
        v-if="nodeType === 'subagent'"
        type="button"
        class="exec-inspect-btn"
        :disabled="!canExpand || loadState === 'loading'"
        :title="!canExpand ? 'Internal trace is not available for this run' : ''"
        :aria-label="expanded ? 'Hide internal process' : 'View internal process'"
        @click.stop="handleClick"
      >
        <svg v-if="!expanded" width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
          <path d="M2.5 8s2-3.25 5.5-3.25S13.5 8 13.5 8s-2 3.25-5.5 3.25S2.5 8 2.5 8Z"/><circle cx="8" cy="8" r="1.5"/>
        </svg>
        <svg v-else width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
          <path d="m4 4 8 8M12 4l-8 8"/>
        </svg>
        <span>{{ expanded ? 'Hide process' : 'View process' }}</span>
      </button>
    </div>

    <div v-if="expanded && slots.default" class="exec-children">
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
  min-height: 58px;
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 7px 12px 7px calc(10px + var(--exec-depth, 0) * 22px);
  border: 1px solid transparent;
  border-radius: 7px;
  background: transparent;
  color: inherit;
  cursor: pointer;
  text-align: left;
  font-size: 13px;
  transition: background 140ms ease, border-color 140ms ease;
}
.exec-header:hover { background: var(--bg-hover); }
.exec-header.is-expanded { background: color-mix(in srgb, var(--bg-secondary) 60%, transparent); }
.exec-header.is-selected {
  border-color: color-mix(in srgb, var(--text-accent) 32%, var(--border-subtle));
  background: color-mix(in srgb, var(--text-accent) 7%, var(--bg-primary));
  box-shadow: inset 3px 0 0 var(--text-accent);
}
.exec-header[aria-disabled="true"] { cursor: default; }
.exec-header[aria-disabled="true"]:hover { background: transparent; }
.exec-header:focus-visible { outline: 2px solid var(--text-accent); outline-offset: 1px; }
.exec-expand { width: 16px; height: 16px; display: grid; place-items: center; flex-shrink: 0; color: var(--text-tertiary); transition: transform 140ms ease; }
.exec-expand.rotated { transform: rotate(90deg); }
.exec-expand.invisible { visibility: hidden; }
.exec-icon { width: 26px; height: 26px; display: grid; place-items: center; flex-shrink: 0; border: 1px solid var(--border-subtle); border-radius: 7px; background: var(--bg-primary); color: var(--text-secondary); }
.exec-icon svg { width: 15px; height: 15px; fill: none; stroke: currentColor; stroke-width: 1.4; stroke-linecap: round; stroke-linejoin: round; }
.exec-step-number {
  width: 28px;
  height: 28px;
  display: grid;
  place-items: center;
  flex-shrink: 0;
  border: 1px solid var(--border-subtle);
  border-radius: 50%;
  background: var(--bg-primary);
  color: var(--text-secondary);
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 600;
}
.is-selected .exec-step-number {
  border-color: var(--text-accent);
  background: var(--text-accent);
  color: var(--bg-primary);
}
.exec-icon--subagent { color: var(--text-accent); }
.exec-icon--task { color: var(--text-secondary); }
.exec-content { flex: 1; min-width: 0; display: grid; gap: 4px; }
.exec-title-line, .exec-support-line { min-width: 0; display: flex; align-items: center; gap: 8px; }
.exec-type { flex-shrink: 0; color: var(--text-tertiary); font-family: var(--font-mono); font-size: 10px; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; }
.exec-name { flex: 1; min-width: 0; overflow: hidden; color: var(--text-primary); font-weight: 500; text-overflow: ellipsis; white-space: nowrap; }
.exec-support { min-width: 0; overflow: hidden; color: var(--text-tertiary); font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.exec-meta { margin-left: auto; flex-shrink: 0; color: var(--text-tertiary); font-family: var(--font-mono); font-size: 10px; }
.exec-spinner { width: 12px; height: 12px; flex-shrink: 0; border: 1.5px solid var(--border); border-top-color: var(--text-secondary); border-radius: 50%; animation: exec-spin 700ms linear infinite; }
.exec-status { flex-shrink: 0; padding: 2px 7px; border-radius: 5px; font-size: 11px; font-weight: 500; background: var(--bg-secondary); color: var(--text-tertiary); }
.exec-status.status-completed { color: var(--color-success, #22c55e); }
.exec-status.status-running { color: var(--text-accent); }
.exec-status.status-failed { color: var(--color-error, #ef4444); }
.exec-status.status-pending { color: var(--text-tertiary); }
.exec-inspect-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  flex: 0 0 auto;
  min-height: 28px;
  padding: 5px 8px;
  border: 1px solid color-mix(in srgb, var(--text-accent) 28%, var(--border-subtle));
  border-radius: 6px;
  background: color-mix(in srgb, var(--text-accent) 7%, var(--bg-primary));
  color: var(--text-accent);
  font-size: 10px;
  font-weight: 600;
  cursor: pointer;
}
.exec-inspect-btn:hover { border-color: var(--text-accent); background: color-mix(in srgb, var(--text-accent) 13%, var(--bg-primary)); }
.exec-inspect-btn:disabled { opacity: .55; cursor: not-allowed; }
.exec-inspect-btn:focus-visible { outline: 2px solid var(--text-accent); outline-offset: 2px; }
.exec-children { margin-top: 1px; }
@keyframes exec-spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .exec-expand { transition: none; } .exec-spinner { animation: none; } }
@media (max-width: 640px) {
  .exec-header { gap: 5px; padding-right: 6px; }
  .exec-support { display: none; }
  .exec-meta { margin-left: 0; }
  .exec-inspect-btn span { display: none; }
  .exec-inspect-btn { padding: 6px; }
}
</style>
