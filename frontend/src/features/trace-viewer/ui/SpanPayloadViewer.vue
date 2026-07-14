<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  payload: { type: String, default: null },
  label: { type: String, default: '' },
})

const expanded = ref(false)
const PREVIEW_LIMIT = 500

const isLong = computed(() => (props.payload || '').length > PREVIEW_LIMIT)
const displayText = computed(() => {
  if (!props.payload) return ''
  if (!expanded.value && isLong.value) {
    return props.payload.slice(0, PREVIEW_LIMIT) + '...'
  }
  return props.payload
})
</script>

<template>
  <div class="payload-viewer" v-if="payload">
    <div class="payload-label" v-if="label">{{ label }}</div>
    <pre class="payload-content">{{ displayText }}</pre>
    <button
      v-if="isLong"
      type="button"
      class="payload-toggle"
      :aria-expanded="expanded"
      @click.stop="expanded = !expanded"
    >
      {{ expanded ? '收起' : '展开全部' }}
    </button>
  </div>
</template>

<style scoped>
.payload-viewer {
  margin-top: 7px;
}
.payload-label {
  margin-bottom: 4px;
  color: var(--text-tertiary);
  font-size: 9px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.payload-content {
  max-height: 300px;
  margin: 0;
  overflow-y: auto;
  padding: 8px 9px;
  border: 1px solid var(--border-subtle);
  border-radius: 7px;
  background: var(--bg-primary);
  color: var(--text-secondary);
  font-family: var(--font-mono);
  font-size: 10px;
  line-height: 1.55;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}
.payload-toggle {
  margin-top: 4px;
  padding: 3px 5px;
  border: none;
  border-radius: 5px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 10px;
  cursor: pointer;
  transition: color 150ms ease, background 150ms ease;
}
.payload-toggle:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}
.payload-toggle:focus-visible {
  outline: 2px solid var(--text-accent);
  outline-offset: 2px;
}
</style>
