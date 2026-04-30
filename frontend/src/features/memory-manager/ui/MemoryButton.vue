<script setup>
defineProps({
  disabled: { type: Boolean, default: false },
})
const emit = defineEmits(['click'])
</script>

<template>
  <button
    class="toolbar-btn"
    :disabled="disabled"
    data-tooltip="Rule"
    title="Project Rules — View and edit CLAUDE.md and rules"
    @click="emit('click')"
  >
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
      <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
      <line x1="8" y1="7" x2="16" y2="7"/>
      <line x1="8" y1="11" x2="14" y2="11"/>
    </svg>
  </button>
</template>

<style scoped>
.toolbar-btn {
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
.toolbar-btn:hover:not(:disabled) {
  color: var(--accent);
  background: var(--layer-active);
  border-color: var(--accent);
  box-shadow: var(--shadow-sm);
}
.toolbar-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.toolbar-btn:active:not(:disabled) {
  transform: scale(0.96);
  transition-duration: 100ms;
}
.toolbar-btn[data-tooltip]::after {
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
.toolbar-btn[data-tooltip]:hover:not(:disabled)::after {
  opacity: 1;
  transform: translateX(-50%) scale(1);
}
</style>
