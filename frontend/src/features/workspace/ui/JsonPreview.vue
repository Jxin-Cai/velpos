<script setup>
import { computed } from 'vue'
import { escapeHtml } from '@shared/lib/escapeHtml'
import hljs from 'highlight.js/lib/common'

const props = defineProps({
  content: { type: String, default: '' },
  zoom: { type: Number, default: 1 },
})

const formatted = computed(() => {
  try {
    return JSON.stringify(JSON.parse(props.content), null, 2)
  } catch {
    return props.content
  }
})

const highlighted = computed(() => {
  try {
    return hljs.highlight(formatted.value, { language: 'json' }).value
  } catch {
    return escapeHtml(formatted.value)
  }
})
</script>

<template>
  <pre class="json-preview" :style="{ fontSize: `${12.5 * zoom}px` }"><code v-html="highlighted"></code></pre>
</template>

<style scoped>
.json-preview {
  flex: 1;
  min-height: 0;
  overflow: auto;
  margin: 0;
  padding: 18px 20px 40px;
  box-sizing: border-box;
  color: var(--text-primary);
  background: var(--bg-primary);
  font-family: var(--font-mono);
  line-height: 1.65;
  white-space: pre;
}
</style>
