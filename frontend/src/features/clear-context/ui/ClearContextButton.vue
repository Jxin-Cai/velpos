<script setup>
import { ref, onBeforeUnmount } from 'vue'

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
let timer = null

function startTimer() {
  clearTimer()
  timer = setTimeout(() => {
    confirming.value = false
  }, 3000)
}

function clearTimer() {
  if (timer) {
    clearTimeout(timer)
    timer = null
  }
}

function handleClick() {
  if (props.disabled || props.clearing) return
  if (!confirming.value) {
    confirming.value = true
    startTimer()
    return
  }
  confirming.value = false
  clearTimer()
  emit('clear')
}

onBeforeUnmount(() => {
  clearTimer()
})
</script>

<template>
  <button
    class="clear-ctx-btn"
    :class="{
      'clear-ctx-btn--confirming': confirming,
      'clear-ctx-btn--disabled': disabled || clearing,
    }"
    :disabled="disabled || clearing"
    @click="handleClick"
    data-tooltip="Clear"
    title="Clear context"
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
  display: inline-flex;
  align-items: center;
  gap: 5px;
  background: linear-gradient(135deg, color-mix(in srgb, var(--accent) 12%, transparent), transparent);
  color: var(--text-secondary);
  border: 1px solid color-mix(in srgb, var(--accent) 34%, var(--border));
  padding: 6px 8px;
  min-height: 30px;
  border-radius: var(--radius-md);
  font-size: 11px;
  cursor: pointer;
  backdrop-filter: blur(calc(var(--glass-blur) * 0.8)) saturate(var(--glass-saturate));
  -webkit-backdrop-filter: blur(calc(var(--glass-blur) * 0.8)) saturate(var(--glass-saturate));
  transition:
    color var(--transition-fast),
    background var(--transition-fast),
    border-color var(--transition-fast),
    box-shadow var(--transition-fast),
    transform var(--transition-fast);
  font-family: var(--font-sans);
  white-space: nowrap;
}


.clear-ctx-btn:hover:not(:disabled) {
  color: var(--accent);
  background: var(--layer-active);
  border-color: var(--accent);
  box-shadow: var(--shadow-sm);
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

.clear-ctx-btn:active:not(:disabled) {
  transform: scale(0.96);
  transition-duration: 100ms;
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

.clear-ctx-btn[data-tooltip]:hover:not(:disabled)::after {
  opacity: 1;
  transform: translateX(-50%) scale(1);
}

.clear-ctx-btn--confirming[data-tooltip]::after {
  display: none;
}
</style>
