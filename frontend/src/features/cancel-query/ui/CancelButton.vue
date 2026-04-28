<script setup>
defineProps({
  visible: {
    type: Boolean,
    required: true,
  },
  pending: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['cancel'])
</script>

<template>
  <Transition name="cancel-pop">
    <button
      v-show="visible"
      type="button"
      class="cancel-btn"
      :class="{ 'cancel-btn--pending': pending }"
      :disabled="pending"
      :aria-busy="pending"
      :title="pending ? 'Cancelling current task...' : 'Cancel current task'"
      @click="emit('cancel')"
    >
      <span v-if="pending" class="cancel-spinner" aria-hidden="true"></span>
      <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <rect x="4" y="4" width="16" height="16" rx="2"/>
      </svg>
      {{ pending ? 'Cancelling...' : 'Cancel' }}
    </button>
  </Transition>
</template>

<style scoped>
.cancel-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-left: auto;
  background: var(--red);
  color: white;
  border: 1px solid var(--red);
  padding: 6px 16px;
  border-radius: var(--radius-sm);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
  animation: cancel-pulse 2s ease-in-out infinite;
}

.cancel-btn:hover:not(:disabled) {
  filter: brightness(1.15);
  box-shadow: var(--shadow-md), 0 0 12px var(--red-dim);
  transform: translateY(-1px);
}

.cancel-btn:active:not(:disabled) {
  transform: translateY(0) scale(0.97);
  filter: brightness(0.95);
  transition-duration: 100ms;
}

.cancel-btn:disabled {
  cursor: wait;
}

.cancel-btn--pending {
  filter: brightness(0.95);
  animation: none;
}

.cancel-spinner {
  width: 12px;
  height: 12px;
  border: 2px solid rgba(255, 255, 255, 0.45);
  border-top-color: white;
  border-radius: 50%;
  animation: cancel-spin 700ms linear infinite;
}

@keyframes cancel-spin {
  to { transform: rotate(360deg); }
}

@keyframes cancel-pulse {
  0%, 100% { box-shadow: 0 0 0 0 var(--red-dim); }
  50% { box-shadow: 0 0 0 4px var(--red-dim); }
}

/* Entry/exit transition */
.cancel-pop-enter-active {
  transition: opacity 200ms var(--ease-smooth), transform 200ms var(--ease-spring);
}

.cancel-pop-leave-active {
  transition: opacity 150ms var(--ease-smooth), transform 150ms var(--ease-smooth);
}

.cancel-pop-enter-from {
  opacity: 0;
  transform: scale(0.9);
}

.cancel-pop-leave-to {
  opacity: 0;
  transform: scale(0.95);
}
</style>
