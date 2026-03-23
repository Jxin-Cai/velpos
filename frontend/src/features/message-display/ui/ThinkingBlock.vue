<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  block: {
    type: Object,
    required: true,
  },
})

const expanded = ref(false)

const truncatedText = computed(() => {
  const text = props.block.thinking || ''
  if (text.length > 300) return text.substring(0, 300) + '...'
  return text
})
</script>

<template>
  <div class="thinking-block" :class="{ 'is-expanded': expanded }">
    <div class="thinking-summary" @click="expanded = !expanded">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="10"/>
        <path d="M12 16v-4"/>
        <path d="M12 8h.01"/>
      </svg>
      <span>Thinking</span>
      <svg class="chevron" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="6 9 12 15 18 9"></polyline>
      </svg>
    </div>
    <div class="thinking-content-wrapper">
      <div class="thinking-content">{{ truncatedText }}</div>
    </div>
  </div>
</template>

<style scoped>
.thinking-block {
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 0;
  margin: 4px 0;
  background: var(--bg-tertiary);
  overflow: hidden;
}

.thinking-summary {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  font-size: 12px;
  color: var(--text-muted);
  cursor: pointer;
  user-select: none;
  transition: background var(--transition-fast), color var(--transition-fast);
}

.thinking-summary:hover {
  color: var(--text-secondary);
  background: var(--bg-hover);
}

.chevron {
  margin-left: auto;
  transition: transform var(--transition-base);
}

.is-expanded .chevron {
  transform: rotate(180deg);
}

.thinking-content-wrapper {
  display: grid;
  grid-template-rows: 0fr;
  transition: grid-template-rows var(--transition-base);
}

.is-expanded .thinking-content-wrapper {
  grid-template-rows: 1fr;
}

.thinking-content {
  min-height: 0;
  padding: 0 10px;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  opacity: 0;
  transition: opacity var(--transition-fast), padding var(--transition-base);
}

.is-expanded .thinking-content {
  opacity: 1;
  padding: 8px 10px;
  border-top: 1px solid var(--border);
}
</style>
