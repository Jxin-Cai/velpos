<script setup>
const props = defineProps({
  channelName: {
    type: String,
    default: '',
  },
  description: {
    type: String,
    default: '',
  },
  prompt: {
    type: String,
    default: '',
  },
  disabled: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['start', 'back'])
</script>

<template>
  <div class="prompt-binder">
    <button class="back-link" @click="emit('back')">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="15 18 9 12 15 6" />
      </svg>
      Back
    </button>
    <div class="prompt-info">
      <p class="prompt-desc">
        Bind <strong>{{ channelName }}</strong> to this session.
        {{ description || 'After starting, the session will listen for messages from this channel.' }}
      </p>
      <div class="warning-hint">
        The session will be dedicated to handling channel messages during listening.
      </div>
    </div>
    <button
      class="btn-start"
      :disabled="disabled"
      @click="emit('start', prompt)"
    >
      Start Binding
    </button>
  </div>
</template>

<style scoped>
.prompt-binder {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.back-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: none;
  border: none;
  color: var(--text-muted);
  font-size: 12px;
  cursor: pointer;
  padding: 0;
  align-self: flex-start;
  transition: color 0.15s;
}

.back-link:hover {
  color: var(--text-primary);
}

.prompt-info {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.prompt-desc {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
  margin: 0;
}

.prompt-preview {
  background: var(--bg-tertiary);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  overflow: hidden;
}

.preview-label {
  font-size: 10px;
  color: var(--text-muted);
  padding: 6px 10px;
  border-bottom: 1px solid var(--border);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.preview-text {
  font-size: 12px;
  color: var(--text-secondary);
  padding: 10px;
  margin: 0;
  white-space: pre-wrap;
  font-family: var(--font-mono);
  line-height: 1.5;
  max-height: 160px;
  overflow-y: auto;
}

.warning-hint {
  font-size: 12px;
  color: var(--yellow, #f59e0b);
  background: var(--yellow-dim, rgba(245, 158, 11, 0.1));
  padding: 8px 12px;
  border-radius: var(--radius-sm);
  line-height: 1.5;
}

.btn-start {
  align-self: center;
  padding: 8px 28px;
  border: 1px solid var(--accent);
  border-radius: var(--radius-sm);
  background: var(--accent-dim);
  color: var(--accent);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}

.btn-start:hover:not(:disabled) {
  background: var(--accent);
  color: var(--text-on-accent);
}

.btn-start:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
