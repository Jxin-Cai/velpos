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
    class="glass-btn glass-btn--accent cmd-btn"
    :disabled="disabled"
    @click="emit('click')"
    data-tooltip="Skills"
    title="View available commands"
    aria-label="View available commands and skills"
  >
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <polyline points="4 17 10 11 4 5" />
      <line x1="12" y1="19" x2="20" y2="19" />
    </svg>
  </button>
</template>

<style scoped>
.cmd-btn {
  position: relative;
  padding: 6px 8px;
  min-height: 30px;
}

.cmd-btn::before {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(120deg, transparent, color-mix(in srgb, var(--accent) 18%, transparent), transparent);
  transform: translateX(-120%);
  transition: transform 420ms ease;
}

.cmd-btn:hover:not(:disabled)::before {
  transform: translateX(120%);
}

.cmd-btn > * {
  position: relative;
}

.cmd-btn[data-tooltip]::after {
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

.cmd-btn[data-tooltip]:is(:hover, :focus-visible)::after {
  opacity: 1;
  transform: translateX(-50%) scale(1);
}
</style>
