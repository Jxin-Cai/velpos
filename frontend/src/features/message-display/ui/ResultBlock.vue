<script setup>
import { formatDuration } from '../lib/formatters'

defineProps({
  result: {
    type: Object,
    required: true,
  },
})
</script>

<template>
  <!-- Only show for errors; normal completions are tracked in History -->
  <div v-if="result.meta?.is_error" class="msg-result error">
    <div class="result-divider">
      <div class="divider-line"></div>
      <div class="result-badge">
        <span class="result-dot"></span>
        <span class="result-label">Error</span>
      </div>
      <div class="divider-line"></div>
    </div>
    <div v-if="result.html" class="result-text markdown-body" v-html="result.html"></div>
  </div>
</template>

<style scoped>
.msg-result {
  margin: 8px 0 4px;
}

.result-divider {
  display: flex;
  align-items: center;
  gap: 12px;
}

.divider-line {
  flex: 1;
  height: 1px;
  background: var(--border);
}

.msg-result.error .divider-line {
  background: var(--red-dim);
}

.result-badge {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 2px 10px;
  border-radius: 99px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border);
}

.msg-result.error .result-badge {
  border-color: var(--red-dim);
  background: var(--red-dim);
}

.result-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--green);
}

.msg-result.error .result-dot {
  background: var(--red);
}

.result-label {
  font-weight: 600;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-muted);
}

.msg-result.error .result-label {
  color: var(--red);
}

.result-meta {
  display: flex;
  justify-content: center;
  gap: 16px;
  padding: 4px 0;
  font-size: 11px;
  font-family: var(--font-mono);
  color: var(--text-muted);
}

.meta-item {
  display: flex;
  align-items: center;
}

.result-text {
  padding: 8px 0 0;
  color: var(--text-secondary);
  font-size: 13px;
}
</style>
