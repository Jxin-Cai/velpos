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
      Clear
    </template>
  </button>
</template>

<style scoped>
.clear-ctx-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: transparent;
  color: var(--text-secondary);
  border: 1px solid var(--border);
  padding: 3px 8px;
  height: 28px;
  border-radius: var(--radius-sm);
  font-size: 11px;
  cursor: pointer;
  transition: all var(--transition-fast);
  font-family: var(--font-sans);
  white-space: nowrap;
}

.clear-ctx-btn:hover:not(:disabled) {
  color: var(--text-primary);
  background: var(--bg-hover);
  border-color: var(--accent);
}

.clear-ctx-btn--confirming {
  color: var(--red);
  background: var(--red-dim);
}

.clear-ctx-btn--confirming:hover:not(:disabled) {
  background: var(--red-dim);
  filter: brightness(1.3);
}

.clear-ctx-btn--disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
</style>
