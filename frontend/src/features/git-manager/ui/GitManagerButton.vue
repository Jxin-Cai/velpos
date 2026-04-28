<script setup>
const emit = defineEmits(['click'])
</script>

<template>
  <button
    class="git-btn"
    @click="emit('click')"
    title="Git Management"
  >
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <line x1="6" y1="3" x2="6" y2="15"/>
      <circle cx="18" cy="6" r="3"/>
      <circle cx="6" cy="18" r="3"/>
      <path d="M18 9a9 9 0 0 1-9 9"/>
    </svg>
    <span class="git-btn-label">Git</span>
  </button>
</template>

<style scoped>
.git-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 9px;
  min-height: 32px;
  border: 1px solid color-mix(in srgb, var(--glass-border) 70%, transparent);
  border-radius: var(--radius-md);
  background: color-mix(in srgb, var(--glass-bg) 36%, transparent);
  color: var(--text-secondary);
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

.git-btn:hover {
  background: var(--layer-active);
  color: var(--accent);
  border-color: var(--accent);
  box-shadow: var(--shadow-sm);
}

.git-btn:active {
  transform: scale(0.96);
  transition-duration: 100ms;
}

.git-btn-label {
  font-weight: 500;
}

@media (max-width: 768px) {
  .git-btn-label {
    display: none;
  }
}
</style>
