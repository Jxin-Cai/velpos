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
  gap: 4px;
  padding: 3px 8px;
  height: 28px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  font-size: 11px;
  cursor: pointer;
  transition:
    color var(--transition-fast),
    background var(--transition-fast),
    border-color var(--transition-fast);
  font-family: var(--font-sans);
  white-space: nowrap;
}

.git-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
  border-color: var(--accent);
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
