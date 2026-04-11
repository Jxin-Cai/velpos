<script setup>
import { computed, onBeforeUnmount } from 'vue'
import { useVoiceInput } from '../model/useVoiceInput'

const props = defineProps({
  disabled: { type: Boolean, default: false },
})

const emit = defineEmits(['text'])

const { isRecording, supported, stopRecording, toggle } = useVoiceInput()

const isDisabled = computed(() => (!supported.value || props.disabled) && !isRecording.value)

function handleToggle() {
  toggle((text) => emit('text', text))
}

onBeforeUnmount(() => {
  stopRecording()
})
</script>

<template>
  <button
    class="toolbar-btn"
    :class="{ 'toolbar-btn--recording': isRecording }"
    :disabled="isDisabled"
    :title="!supported ? 'Voice input not supported in this browser' : isRecording ? 'Stop recording' : 'Start voice input'"
    @click="handleToggle"
  >
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
      <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
      <line x1="12" y1="19" x2="12" y2="23"/>
      <line x1="8" y1="23" x2="16" y2="23"/>
    </svg>
    <span v-if="isRecording" class="recording-dot"></span>
    <span class="toolbar-btn-label">{{ isRecording ? 'Stop' : 'Voice' }}</span>
  </button>
</template>

<style scoped>
.toolbar-btn {
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
  transition: color var(--transition-fast), background var(--transition-fast), border-color var(--transition-fast);
  font-family: var(--font-sans);
  white-space: nowrap;
  position: relative;
}
.toolbar-btn:hover:not(:disabled) {
  color: var(--text-primary);
  background: var(--bg-hover);
  border-color: var(--accent);
}
.toolbar-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.toolbar-btn--recording {
  color: var(--red);
  border-color: var(--red);
  background: var(--red-dim);
}
.toolbar-btn-label {
  font-weight: 500;
}
.recording-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--red);
  animation: pulse-dot 1s ease-in-out infinite;
}
@keyframes pulse-dot {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}
</style>
