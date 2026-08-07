<script setup>
defineProps({
  zoom: { type: Number, required: true },
  fullscreen: { type: Boolean, default: false },
})

defineEmits(['zoom-out', 'zoom-reset', 'zoom-in', 'toggle-fullscreen'])
</script>

<template>
  <div class="preview-controls" role="group" aria-label="Preview display controls">
    <button
      type="button"
      :disabled="zoom <= 0.5"
      aria-label="Zoom out"
      title="Zoom out"
      @click="$emit('zoom-out')"
    >
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
        <circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3M8 11h6"/>
      </svg>
    </button>
    <button
      type="button"
      class="preview-zoom-value"
      :disabled="zoom === 1"
      :aria-label="`Reset zoom, currently ${Math.round(zoom * 100)}%`"
      title="Reset to 100%"
      @click="$emit('zoom-reset')"
    >
      <svg v-if="zoom !== 1" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
        <path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/>
      </svg>
      {{ Math.round(zoom * 100) }}%
    </button>
    <button
      type="button"
      :disabled="zoom >= 2"
      aria-label="Zoom in"
      title="Zoom in"
      @click="$emit('zoom-in')"
    >
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
        <circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3M11 8v6M8 11h6"/>
      </svg>
    </button>
    <span class="preview-control-divider" aria-hidden="true"></span>
    <button
      type="button"
      class="preview-fullscreen-button"
      :aria-label="fullscreen ? 'Exit expanded preview' : 'Expand preview'"
      :title="fullscreen ? 'Exit expanded preview' : 'Expand preview'"
      @click="$emit('toggle-fullscreen')"
    >
      <svg v-if="!fullscreen" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
        <path d="M8 3H5a2 2 0 0 0-2 2v3M16 3h3a2 2 0 0 1 2 2v3M8 21H5a2 2 0 0 1-2-2v-3M16 21h3a2 2 0 0 0 2-2v-3"/>
      </svg>
      <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
        <path d="M8 3v3a2 2 0 0 1-2 2H3M16 3v3a2 2 0 0 0 2 2h3M8 21v-3a2 2 0 0 0-2-2H3M16 21v-3a2 2 0 0 1 2-2h3"/>
      </svg>
      <span>{{ fullscreen ? 'Exit expanded view' : 'Expand preview' }}</span>
    </button>
  </div>
</template>

<style scoped>
.preview-controls {
  display: inline-flex;
  min-height: 38px;
  align-items: center;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-primary);
}

.preview-controls button {
  min-width: 38px;
  height: 38px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 0 7px;
  border: 0;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font: 600 11px/1 var(--font-sans);
  transition: color var(--transition-fast), background var(--transition-fast);
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

.preview-controls button:disabled {
  cursor: default;
  opacity: 0.45;
}

.preview-zoom-value {
  min-width: 58px !important;
  font-variant-numeric: tabular-nums;
}

.preview-fullscreen-button {
  min-width: 132px !important;
  color: var(--accent) !important;
  background: var(--accent-dim) !important;
  box-shadow: inset 1px 0 0 var(--border-subtle);
}

.preview-control-divider {
  width: 1px;
  height: 18px;
  background: var(--border-subtle);
}

@media (max-width: 1280px) {
  .preview-fullscreen-button {
    min-width: 38px !important;
  }

  .preview-fullscreen-button span {
    display: none;
  }
}
</style>
