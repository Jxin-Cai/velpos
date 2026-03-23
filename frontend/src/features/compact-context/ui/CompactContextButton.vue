<script setup>
defineProps({
  disabled: {
    type: Boolean,
    default: false,
  },
  compacting: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['compact'])
</script>

<template>
  <button
    class="compact-btn"
    :disabled="disabled || compacting"
    @click="emit('compact')"
    title="Compact context"
  >
    <svg v-if="!compacting" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <polyline points="4 14 10 14 10 20"/>
      <polyline points="20 10 14 10 14 4"/>
      <line x1="14" y1="10" x2="21" y2="3"/>
      <line x1="3" y1="21" x2="10" y2="14"/>
    </svg>
    <span v-else class="spinner-sm"></span>
    <span class="compact-btn-label">
      {{ compacting ? 'Compacting...' : 'Compact' }}
    </span>
  </button>
</template>

<style scoped>
.compact-btn {
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

.compact-btn:hover:not(:disabled) {
  color: var(--text-primary);
  background: var(--bg-hover);
  border-color: var(--accent);
}

.compact-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.compact-btn-label {
  font-weight: 500;
}

.spinner-sm {
  width: 12px;
  height: 12px;
  border: 2px solid currentColor;
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
