<script setup>
import { formatDuration } from '@shared/lib/formatTime'

const props = defineProps({
  items: { type: Array, default: () => [] },
  label: { type: String, default: 'Subagent chain' },
  activeSpanId: { type: String, default: null },
})

const emit = defineEmits(['open-subagent'])

function isActive(item) {
  return Boolean(props.activeSpanId) && item.span_id === props.activeSpanId
}

function displayName(item) {
  return item?.subagent || item?.agent_id || 'Subagent'
}

function stepLabel(item) {
  if (item.stepSequence == null) return 'Not linked to a step'
  return `Task ${item.taskSequence} · Step ${item.stepSequence}`
}
</script>

<template>
  <nav v-if="items.length" class="agent-chain" :aria-label="`${label}, in call order`">
    <div class="agent-chain-label">
      <span>{{ label }}</span>
      <strong>{{ items.length }}</strong>
    </div>
    <ol class="agent-chain-list">
      <li v-for="item in items" :key="item.key">
        <button
          type="button"
          class="agent-chain-item"
          :class="[`status-${item.status || 'recorded'}`, { 'is-active': isActive(item) }]"
          :disabled="!item.span_id"
          :aria-current="isActive(item) ? 'true' : undefined"
          :title="item.span_id ? `Open ${displayName(item)} execution steps` : 'Internal trace is not available for this subagent'"
          @click="emit('open-subagent', item)"
        >
          <span class="agent-chain-order">{{ item.order }}</span>
          <span class="agent-chain-body">
            <strong>{{ displayName(item) }}</strong>
            <small v-if="isActive(item)" class="agent-chain-current">Viewing this subagent</small>
            <small v-else>{{ stepLabel(item) }}<template v-if="item.duration_ms"> · {{ formatDuration(item.duration_ms) }}</template></small>
          </span>
          <svg class="agent-chain-open" width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
            <path d="m6 4 4 4-4 4" />
          </svg>
        </button>
      </li>
    </ol>
  </nav>
</template>

<style scoped>
.agent-chain {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: center;
  gap: 10px;
  margin: 6px 8px 8px;
  padding: 7px 10px;
  border: 1px solid color-mix(in srgb, var(--text-accent) 22%, var(--border-subtle));
  border-radius: 9px;
  background: color-mix(in srgb, var(--text-accent) 4%, var(--bg-primary));
}
.agent-chain-label { display: grid; gap: 1px; }
.agent-chain-label span {
  color: var(--text-accent);
  font-family: var(--font-mono);
  font-size: 8px;
  font-weight: 700;
  letter-spacing: .07em;
  text-transform: uppercase;
}
.agent-chain-label strong { color: var(--text-secondary); font-family: var(--font-mono); font-size: 11px; }
.agent-chain-list {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 4px;
  margin: 0;
  padding: 1px 1px 3px;
  overflow-x: auto;
  list-style: none;
  scrollbar-width: thin;
}
.agent-chain-list li { display: flex; align-items: center; flex: 0 0 auto; }
/* The arrow reads as the handoff from one delegated agent to the next. */
.agent-chain-list li + li::before {
  flex: 0 0 auto;
  margin: 0 3px;
  color: color-mix(in srgb, var(--text-accent) 60%, var(--text-tertiary));
  font-size: 11px;
  content: '→';
}
.agent-chain-item {
  min-width: 168px;
  max-width: 250px;
  min-height: 40px;
  display: grid;
  grid-template-columns: 20px minmax(0, 1fr) 12px;
  align-items: center;
  gap: 7px;
  padding: 5px 8px;
  border: 1px solid var(--border-subtle);
  border-radius: 7px;
  background: var(--bg-primary);
  color: inherit;
  cursor: pointer;
  text-align: left;
  transition: border-color 160ms ease, background 160ms ease;
}
.agent-chain-item:hover:not(:disabled) {
  border-color: var(--text-accent);
  background: color-mix(in srgb, var(--text-accent) 7%, var(--bg-primary));
}
.agent-chain-item:focus-visible { outline: 2px solid var(--text-accent); outline-offset: 1px; }
.agent-chain-item:disabled { cursor: not-allowed; opacity: .55; }
.agent-chain-order {
  width: 20px;
  height: 20px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: color-mix(in srgb, var(--text-accent) 12%, var(--bg-secondary));
  color: var(--text-accent);
  font-family: var(--font-mono);
  font-size: 9px;
  font-weight: 700;
}
.agent-chain-body { min-width: 0; display: grid; gap: 1px; }
.agent-chain-body strong {
  overflow: hidden;
  color: var(--text-primary);
  font-size: 11px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.agent-chain-body small {
  overflow: hidden;
  color: var(--text-tertiary);
  font-family: var(--font-mono);
  font-size: 8px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.agent-chain-open { color: var(--text-tertiary); }
.agent-chain-item.status-failed .agent-chain-order,
.agent-chain-item.status-error .agent-chain-order {
  background: color-mix(in srgb, var(--color-error, #ef4444) 14%, var(--bg-secondary));
  color: var(--color-error, #ef4444);
}
.agent-chain-item.status-running .agent-chain-order { background: color-mix(in srgb, var(--text-accent) 18%, var(--bg-secondary)); }
.agent-chain-item.is-active {
  border-color: var(--text-accent);
  background: color-mix(in srgb, var(--text-accent) 11%, var(--bg-primary));
  box-shadow: inset 2px 0 0 var(--text-accent);
}
.agent-chain-item.is-active .agent-chain-order { background: var(--text-accent); color: var(--bg-primary); }
.agent-chain-current { color: var(--text-accent) !important; font-weight: 600; }
@media (max-width: 640px) {
  .agent-chain { grid-template-columns: minmax(0, 1fr); }
  .agent-chain-item { min-width: 148px; }
}
@media (prefers-reduced-motion: reduce) { .agent-chain-item { transition: none; } }
</style>
