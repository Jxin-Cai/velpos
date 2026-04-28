<script setup>
defineProps({
  disabled: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['click'])
</script>

<template>
  <button
    class="terminal-btn"
    :disabled="disabled"
    @click="emit('click')"
    title="Terminal"
  >
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <polyline points="4 17 10 11 4 5"/>
      <line x1="12" y1="19" x2="20" y2="19"/>
    </svg>
  </button>
</template>

<style scoped>
.terminal-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 32px;
  padding: 0;
  border: 1px solid color-mix(in srgb, var(--glass-border) 70%, transparent);
  border-radius: var(--radius-md);
  background: color-mix(in srgb, var(--glass-bg) 36%, transparent);
  color: var(--text-secondary);
  cursor: pointer;
  backdrop-filter: blur(calc(var(--glass-blur) * 0.8)) saturate(var(--glass-saturate));
  -webkit-backdrop-filter: blur(calc(var(--glass-blur) * 0.8)) saturate(var(--glass-saturate));
  transition:
    color var(--transition-fast),
    background var(--transition-fast),
    border-color var(--transition-fast),
    box-shadow var(--transition-fast),
    transform var(--transition-fast);
}

.terminal-btn:hover:not(:disabled) {
  background: var(--layer-active);
  color: var(--accent);
  border-color: var(--accent);
  box-shadow: var(--shadow-sm);
}

.terminal-btn:active:not(:disabled) {
  transform: scale(0.96);
  transition-duration: 100ms;
}

.terminal-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

</style>
