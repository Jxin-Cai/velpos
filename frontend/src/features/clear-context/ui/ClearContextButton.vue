<script setup>
import { ref } from 'vue'
import { useTimeout } from '@shared/lib/useTimeout'

const props = defineProps({
  disabled: {
    type: Boolean,
    default: false,
  },
  clearing: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['clear'])

const confirming = ref(false)
const { set: setTimer, clear: clearTimer } = useTimeout()
let timerId = null

function startTimer() {
  if (timerId) clearTimer(timerId)
  timerId = setTimer(() => {
    confirming.value = false
    timerId = null
  }, 3000)
}

function handleClick() {
  if (props.disabled || props.clearing) return
  if (!confirming.value) {
    confirming.value = true
    startTimer()
    return
  }
  confirming.value = false
  if (timerId) { clearTimer(timerId); timerId = null }
  emit('clear')
}
</script>

<template>
  <button
    class="toolbar-btn clear-ctx-btn"
    :class="{
      'clear-ctx-btn--confirming': confirming,
      'clear-ctx-btn--disabled': disabled || clearing,
    }"
    :disabled="disabled || clearing"
    @click="handleClick"
    data-tooltip="Clear"
    title="Clear context"
    aria-label="Clear conversation context"
  >
    <template v-if="clearing">Clearing...</template>
    <template v-else-if="confirming">Confirm?</template>
    <template v-else>
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="3 6 5 6 21 6" />
        <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
        <path d="M10 11v6" />
        <path d="M14 11v6" />
        <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
      </svg>
    </template>
  </button>
</template>

<style scoped>
.clear-ctx-btn {
  position: relative;
  padding: 6px 8px;
  min-height: 30px;
}

.clear-ctx-btn--confirming {
  color: var(--red);
  background: var(--red-dim);
  border-color: var(--red);
  animation: confirm-pulse 1.5s ease-in-out infinite;
}

@keyframes confirm-pulse {
  0%, 100% { box-shadow: 0 0 0 0 var(--red-dim); }
  50% { box-shadow: 0 0 0 3px var(--red-dim); }
}

.clear-ctx-btn--confirming:hover:not(:disabled) {
  background: var(--red-dim);
  filter: brightness(1.3);
}

.clear-ctx-btn--disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.clear-ctx-btn[data-tooltip]::after {
  content: attr(data-tooltip);
  position: absolute;
  bottom: calc(100% + 6px);
  left: 50%;
  transform: translateX(-50%) scale(0.9);
  padding: 3px 8px;
  border-radius: 4px;
  background: var(--bg-secondary);
  color: var(--text-primary);
  font-size: 11px;
  font-family: var(--font-sans);
  font-weight: 500;
  white-space: nowrap;
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.15s, transform 0.15s;
  border: 1px solid var(--border);
  box-shadow: var(--shadow-sm);
  z-index: 100;
}

.clear-ctx-btn[data-tooltip]:is(:hover, :focus-visible)::after {
  opacity: 1;
  transform: translateX(-50%) scale(1);
}

.clear-ctx-btn--confirming[data-tooltip]::after {
  display: none;
}
</style>
