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
    class="cmd-btn"
    :disabled="disabled"
    @click="emit('click')"
    title="View available commands"
  >
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <polyline points="4 17 10 11 4 5" />
      <line x1="12" y1="19" x2="20" y2="19" />
    </svg>
    <span>Skills</span>
  </button>
</template>

<style scoped>
.cmd-btn {
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
  transition:
    color var(--transition-fast),
    background var(--transition-fast),
    border-color var(--transition-fast);
  font-family: var(--font-sans);
  white-space: nowrap;
}

.cmd-btn:hover:not(:disabled) {
  color: var(--text-primary);
  background: var(--bg-hover);
  border-color: var(--accent);
}

.cmd-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
</style>
