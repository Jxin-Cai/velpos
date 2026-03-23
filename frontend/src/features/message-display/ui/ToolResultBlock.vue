<script setup>
import { ref } from 'vue'

defineProps({
  result: {
    type: Object,
    required: true,
  },
})

const expanded = ref(false)
</script>

<template>
  <div class="msg-tool-result" :class="{ error: result.is_error, 'is-expanded': expanded }" @click="expanded = !expanded">
    <div class="tool-result-header">
      <span class="result-icon" :class="result.is_error ? 'error' : 'success'">
        <svg v-if="result.is_error" width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
          <line x1="18" y1="6" x2="6" y2="18"></line>
          <line x1="6" y1="6" x2="18" y2="18"></line>
        </svg>
        <svg v-else width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="20 6 9 17 4 12"></polyline>
        </svg>
      </span>
      <span class="tool-result-label">{{ result.is_error ? 'Error' : 'Result' }}</span>
      <span v-if="result.content" class="expand-hint">
        <svg :class="{ rotated: expanded }" width="10" height="10" viewBox="0 0 16 16" fill="currentColor">
          <path d="M4.646 5.646a.5.5 0 0 1 .708 0L8 8.293l2.646-2.647a.5.5 0 0 1 .708.708l-3 3a.5.5 0 0 1-.708 0l-3-3a.5.5 0 0 1 0-.708z"/>
        </svg>
      </span>
    </div>
    <div class="tool-result-content-wrapper">
      <div class="tool-result-content" v-if="result.content">
        <pre>{{ result.content }}</pre>
      </div>
    </div>
  </div>
</template>

<style scoped>
.msg-tool-result {
  border-radius: var(--radius-sm);
  overflow: hidden;
  cursor: pointer;
  transition: background var(--transition-fast), border-color var(--transition-fast);
  border: 1px solid var(--border-subtle);
  background: var(--bg-tertiary);
  margin-top: 2px;
}

.msg-tool-result:hover {
  background: var(--bg-hover);
  border-color: var(--border);
}

.msg-tool-result.is-expanded {
  border-color: var(--border);
  background: var(--bg-secondary);
}

.msg-tool-result.error {
  border-color: var(--red-dim);
  background: rgba(239, 68, 68, 0.05);
}

.tool-result-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  font-size: 12px;
}

.result-icon {
  width: 14px;
  height: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  flex-shrink: 0;
}

.result-icon.success {
  background: var(--green);
  color: white;
}

.result-icon.error {
  background: var(--red);
  color: white;
}

.tool-result-label {
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 500;
}

.expand-hint {
  margin-left: auto;
  color: var(--text-muted);
  display: flex;
  align-items: center;
}

.expand-hint svg {
  transition: transform var(--transition-base);
}

.expand-hint svg.rotated {
  transform: rotate(180deg);
}

.tool-result-content-wrapper {
  display: grid;
  grid-template-rows: 0fr;
  transition: grid-template-rows var(--transition-base);
}

.is-expanded .tool-result-content-wrapper {
  grid-template-rows: 1fr;
}

.tool-result-content {
  min-height: 0;
  overflow: hidden;
  opacity: 0;
  transition: opacity var(--transition-fast);
}

.is-expanded .tool-result-content {
  opacity: 1;
}

.tool-result-content pre {
  margin: 0 8px 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: 11px;
  max-height: 300px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-all;
  padding: 8px;
  background: var(--bg-primary);
  color: var(--text-secondary);
}

.msg-tool-result.error .tool-result-content pre {
  color: var(--red);
  border-color: var(--red-dim);
}
</style>
