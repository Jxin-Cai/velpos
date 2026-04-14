<script setup>
defineProps({
  visible: {
    type: Boolean,
    required: true,
  },
})

const emit = defineEmits(['cancel'])
</script>

<template>
  <Transition name="cancel-pop">
    <button
      v-show="visible"
      class="cancel-btn"
      @click="emit('cancel')"
    >
      <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
        <rect x="4" y="4" width="16" height="16" rx="2"/>
      </svg>
      Cancel
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

.cancel-btn:hover {
  filter: brightness(1.15);
  box-shadow: var(--shadow-md), 0 0 12px var(--red-dim);
  transform: translateY(-1px);
}

.cancel-btn:active {
  transform: translateY(0) scale(0.97);
  filter: brightness(0.95);
  transition-duration: 80ms;
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
