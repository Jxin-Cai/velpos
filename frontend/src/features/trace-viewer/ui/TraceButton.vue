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
  <span v-if="runId" class="trace-control">
    <button
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
      <span v-if="summary?.subagentCount" class="trace-badge" aria-hidden="true">{{ summary.subagentCount }}</span>
    </button>
    <span v-if="summary?.subagents?.length" class="trace-agent-menu" role="group" aria-label="Subagents used in this run">
      <span class="trace-agent-menu-title">Subagents used</span>
      <button
        v-for="agent in summary.subagents"
        :key="agent.key"
        type="button"
        :disabled="!agent.spanId"
        :aria-label="`Open ${agent.name} execution steps`"
        @click.stop="emit('open-trace', { runId, subagentSpanId: agent.spanId })"
      >
        <span class="trace-agent-dot" :class="`status-${agent.status}`" aria-hidden="true"></span>
        <span>{{ agent.name }}</span>
        <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="m6 4 4 4-4 4"/></svg>
      </button>
    </span>
  </span>
</template>

<style scoped>
.trace-control { position: relative; display: inline-flex; }
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
.trace-agent-menu { position: absolute; z-index: 30; top: -4px; left: calc(100% + 7px); width: max-content; min-width: 190px; max-width: 300px; display: none; gap: 3px; padding: 7px; border: 1px solid var(--border-subtle); border-radius: 9px; background: var(--bg-primary); box-shadow: 0 10px 28px rgba(0, 0, 0, .18); }
.trace-agent-menu::before { content: ''; position: absolute; top: 0; right: 100%; width: 8px; height: 100%; }
.trace-control:hover .trace-agent-menu, .trace-control:focus-within .trace-agent-menu { display: grid; }
.trace-agent-menu-title { padding: 2px 5px 4px; color: var(--text-tertiary); font-size: 9px; font-weight: 650; letter-spacing: .06em; text-transform: uppercase; }
.trace-agent-menu button { min-height: 32px; display: grid; grid-template-columns: 7px minmax(0, 1fr) 11px; align-items: center; gap: 7px; padding: 5px 7px; border: 1px solid transparent; border-radius: 6px; background: transparent; color: var(--text-secondary); cursor: pointer; text-align: left; }
.trace-agent-menu button:hover { border-color: color-mix(in srgb, var(--text-accent) 28%, var(--border-subtle)); background: color-mix(in srgb, var(--text-accent) 7%, var(--bg-secondary)); color: var(--text-primary); }
.trace-agent-menu button:focus-visible { outline: 2px solid var(--text-accent); outline-offset: 1px; }
.trace-agent-menu button:disabled { opacity: .5; cursor: not-allowed; }
.trace-agent-menu button > span:nth-child(2) { overflow: hidden; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.trace-agent-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--text-tertiary); }
.trace-agent-dot.status-running { background: var(--text-accent); }
.trace-agent-dot.status-completed { background: var(--color-success, #22c55e); }
.trace-agent-dot.status-failed { background: var(--color-error, #ef4444); }
@keyframes trace-pulse {
  50% { opacity: 0.35; }
}
@media (prefers-reduced-motion: reduce) {
  .trace-btn--running .trace-status-dot { animation: none; }
}
</style>
