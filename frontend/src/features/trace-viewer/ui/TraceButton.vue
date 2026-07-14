<script setup>
import { computed } from 'vue'

const props = defineProps({
  runId: { type: String, default: '' },
  summary: { type: Object, default: null },
})

const emit = defineEmits(['open-trace'])

const status = computed(() => props.summary?.status || 'available')
const title = computed(() => {
  const parts = [`查看运行 ${props.runId} 的完整链路`]
  if (props.summary) {
    parts.push(`状态: ${status.value}`)
    parts.push(`Subagents: ${props.summary.subagentCount || 0}`)
    parts.push(`Tools: ${props.summary.toolCallCount || 0}`)
  }
  return parts.join(' · ')
})
</script>

<template>
  <button
    v-if="runId"
    type="button"
    class="trace-btn"
    :class="`trace-btn--${status}`"
    :title="title"
    :aria-label="title"
    @click.stop="emit('open-trace', runId)"
  >
    <svg class="trace-icon" width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
      <circle cx="3" cy="3" r="1.5"/>
      <circle cx="8" cy="8" r="1.5"/>
      <circle cx="13" cy="12.5" r="1.5"/>
      <path d="M3 4.5v5A2.5 2.5 0 0 0 5.5 12H11.5M4.5 3H6a2 2 0 0 1 2 2v1.5"/>
    </svg>
    <span class="trace-status-dot" aria-hidden="true"></span>
    <span v-if="summary?.subagentCount" class="trace-badge" aria-hidden="true">
      {{ summary.subagentCount }}
    </span>
  </button>
</template>

<style scoped>
.trace-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  position: relative;
  width: 30px;
  height: 30px;
  padding: 0;
  color: var(--text-tertiary);
  background: transparent;
  border: 1px solid transparent;
  border-radius: 8px;
  cursor: pointer;
  transition: color var(--transition-fast), border-color var(--transition-fast), background var(--transition-fast);
}
.trace-btn:hover {
  color: var(--text-primary);
  border-color: var(--border-subtle);
  background: var(--bg-hover);
}
.trace-btn:focus-visible {
  outline: 2px solid var(--text-accent);
  outline-offset: 2px;
}
.trace-status-dot {
  position: absolute;
  right: 3px;
  bottom: 3px;
  width: 6px;
  height: 6px;
  border: 1px solid var(--bg-primary);
  border-radius: 50%;
  background: var(--text-tertiary);
}
.trace-btn--running {
  color: var(--text-accent);
  background: var(--bg-secondary);
}
.trace-btn--running .trace-status-dot {
  background: var(--text-accent);
  animation: trace-pulse 1.2s ease-in-out infinite;
}
.trace-btn--completed .trace-status-dot { background: var(--color-success, #22c55e); }
.trace-btn--failed .trace-status-dot { background: var(--color-error, #ef4444); }
.trace-btn--cancelled .trace-status-dot,
.trace-btn--denied .trace-status-dot { background: var(--color-warning, #f59e0b); }
.trace-badge {
  position: absolute;
  top: -4px;
  right: -5px;
  min-width: 14px;
  height: 14px;
  padding: 0 3px;
  border-radius: 7px;
  border: 1px solid var(--bg-primary);
  background: var(--text-secondary);
  color: var(--bg-primary);
  font-size: 9px;
  font-weight: 700;
  line-height: 14px;
  text-align: center;
}
@keyframes trace-pulse {
  50% { opacity: 0.35; }
}
@media (prefers-reduced-motion: reduce) {
  .trace-btn--running .trace-status-dot { animation: none; }
}
</style>
