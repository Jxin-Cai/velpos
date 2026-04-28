<script setup>
defineProps({
  active: {
    type: Boolean,
    default: false,
  },
})

defineEmits(['click'])
</script>

<template>
  <button
    class="workspace-button"
    :class="{ active }"
    @click="$emit('click')"
    title="Workspace files"
    aria-label="Workspace files"
  >
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/>
      <path d="M3 10h18"/>
    </svg>
  </button>
</template>

<style scoped>
.workspace-button {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 32px;
  border: 1px solid color-mix(in srgb, var(--glass-border) 70%, transparent);
  border-radius: var(--radius-md);
  background: color-mix(in srgb, var(--glass-bg) 36%, transparent);
  color: var(--text-secondary);
  cursor: pointer;
  backdrop-filter: blur(calc(var(--glass-blur) * 0.8)) saturate(var(--glass-saturate));
  -webkit-backdrop-filter: blur(calc(var(--glass-blur) * 0.8)) saturate(var(--glass-saturate));
  transition: background var(--transition-fast), color var(--transition-fast), border-color var(--transition-fast), box-shadow var(--transition-fast), transform var(--transition-fast);
}

.workspace-button:hover,
.workspace-button.active {
  background: var(--layer-active);
  border-color: var(--accent);
  color: var(--accent);
  box-shadow: var(--shadow-sm);
}

.workspace-button:active {
  transform: scale(0.96);
  transition-duration: 100ms;
}
</style>
