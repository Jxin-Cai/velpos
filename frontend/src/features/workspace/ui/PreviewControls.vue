<script setup>
defineProps({
  fullscreen: { type: Boolean, default: false },
})

defineEmits(['toggle-fullscreen'])
</script>

<template>
  <div class="preview-controls" role="group" aria-label="Preview controls">
    <button
      type="button"
      class="preview-fullscreen-button"
      :aria-label="fullscreen ? 'Exit fullscreen preview' : 'Open fullscreen preview'"
      :title="fullscreen ? 'Exit fullscreen preview' : 'Open fullscreen preview'"
      @click="$emit('toggle-fullscreen')"
    >
      <svg v-if="!fullscreen" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
        <path d="M8 3H5a2 2 0 0 0-2 2v3M16 3h3a2 2 0 0 1 2 2v3M8 21H5a2 2 0 0 1-2-2v-3M16 21h3a2 2 0 0 0 2-2v-3"/>
      </svg>
      <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
        <path d="M8 3v3a2 2 0 0 1-2 2H3M16 3v3a2 2 0 0 0 2 2h3M8 21v-3a2 2 0 0 0-2-2H3M16 21v-3a2 2 0 0 1 2-2h3"/>
      </svg>
      <span>{{ fullscreen ? 'Exit fullscreen' : 'Fullscreen' }}</span>
    </button>
  </div>
</template>

<style scoped>
.preview-controls {
  display: inline-flex;
  min-height: 44px;
  align-items: center;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--bg-primary);
}

.preview-controls button {
  min-width: 44px;
  min-height: 44px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 0 12px;
  border: 0;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font: 600 11px/1 var(--font-sans);
  transition: color 180ms ease, background 180ms ease, border-color 180ms ease;
}

.preview-controls button:hover:not(:disabled) {
  color: var(--text-primary);
  background: var(--layer-active);
}

.preview-controls button:focus-visible {
  position: relative;
  z-index: 1;
  outline: 2px solid var(--accent);
  outline-offset: -2px;
}

.preview-fullscreen-button {
  background: var(--accent-dim) !important;
  color: var(--accent) !important;
}

@media (max-width: 1280px) {
  .preview-fullscreen-button {
    min-width: 38px !important;
  }

  .preview-fullscreen-button span {
    display: none;
  }
}

@media (max-width: 620px) {
  .preview-fullscreen-button {
    min-width: 44px !important;
    padding: 0;
  }

  .preview-fullscreen-button span {
    display: none;
  }
}

@media (prefers-reduced-motion: reduce) {
  .preview-controls button {
    transition: none;
  }
}
</style>
