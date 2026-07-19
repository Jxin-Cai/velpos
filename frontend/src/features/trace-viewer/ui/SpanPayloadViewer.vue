<script setup>
import { ref, computed } from 'vue'
import hljs from 'highlight.js/lib/common'

const props = defineProps({
  payload: { type: [String, Number, Boolean, Array, Object], default: null },
  label: { type: String, default: '' },
})

const expanded = ref(false)
const enlarged = ref(false)
const copied = ref(false)
const PREVIEW_LIMIT = 1600

const normalizedPayload = computed(() => {
  if (props.payload == null) return ''
  let value = props.payload
  if (typeof value === 'string') {
    try {
      value = JSON.parse(value)
    } catch (error) {
      if (!(error instanceof SyntaxError)) throw error
    }
  }
  return value
})
const formattedPayload = computed(() => {
  const serialized = JSON.stringify(normalizedPayload.value, null, 2)
  return serialized ?? String(normalizedPayload.value)
})
const isLong = computed(() => formattedPayload.value.length > PREVIEW_LIMIT)
const displayText = computed(() => {
  if (!formattedPayload.value) return ''
  if (!expanded.value && isLong.value) {
    return formattedPayload.value.slice(0, PREVIEW_LIMIT) + '…'
  }
  return formattedPayload.value
})
const highlightedPayload = computed(() => (
  displayText.value
    ? hljs.highlight(displayText.value, { language: 'json', ignoreIllegals: true }).value
    : ''
))
const fullHighlightedPayload = computed(() => (
  formattedPayload.value
    ? hljs.highlight(formattedPayload.value, { language: 'json', ignoreIllegals: true }).value
    : ''
))
const lineCount = computed(() => displayText.value ? displayText.value.split('\n').length : 0)
const valueType = computed(() => {
  if (Array.isArray(normalizedPayload.value)) return 'array'
  if (normalizedPayload.value === null) return 'null'
  return typeof normalizedPayload.value === 'object' ? 'object' : typeof normalizedPayload.value
})

async function copyPayload() {
  try {
    await navigator.clipboard.writeText(formattedPayload.value)
  } catch {
    const textarea = document.createElement('textarea')
    textarea.value = formattedPayload.value
    textarea.style.position = 'fixed'
    textarea.style.opacity = '0'
    document.body.appendChild(textarea)
    textarea.select()
    document.execCommand('copy')
    textarea.remove()
  }
  copied.value = true
  window.setTimeout(() => { copied.value = false }, 1600)
}
</script>

<template>
  <section v-if="payload != null" class="payload-viewer">
    <header class="payload-header">
      <span v-if="label" class="payload-label">{{ label }}</span>
      <span class="payload-language">JSON</span>
      <span class="payload-meta">{{ valueType }} · {{ lineCount }} lines</span>
      <div class="payload-actions">
        <button type="button" class="payload-action" :title="copied ? 'Copied' : 'Copy JSON'" @click.stop="copyPayload">
          <svg v-if="!copied" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.35" aria-hidden="true"><rect x="5" y="5" width="7.5" height="8" rx="1.3"/><path d="M10.5 5V3.7A1.2 1.2 0 0 0 9.3 2.5H4.7a1.2 1.2 0 0 0-1.2 1.2v7.1A1.2 1.2 0 0 0 4.7 12H5"/></svg>
          <svg v-else viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="m3.5 8.2 3 3 6-6"/></svg>
          <span>{{ copied ? 'Copied' : 'Copy' }}</span>
        </button>
        <button type="button" class="payload-action" title="Open large JSON viewer" @click.stop="enlarged = true">
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.35" aria-hidden="true"><path d="M5.5 2.5H2.5v3M10.5 2.5h3v3M5.5 13.5H2.5v-3M10.5 13.5h3v-3"/><path d="m2.8 5.2 2.7-2.7M13.2 5.2l-2.7-2.7M2.8 10.8l2.7 2.7M13.2 10.8l-2.7 2.7"/></svg>
          <span>Expand</span>
        </button>
      </div>
    </header>
    <pre class="payload-content"><code v-html="highlightedPayload"></code></pre>
    <button
      v-if="isLong"
      type="button"
      class="payload-toggle"
      :aria-expanded="expanded"
      @click.stop="expanded = !expanded"
    >
      {{ expanded ? 'Collapse JSON' : `Show complete JSON (${formattedPayload.length.toLocaleString()} chars)` }}
    </button>
  </section>
  <Teleport to="body">
    <div v-if="enlarged" class="payload-modal" role="dialog" aria-modal="true" :aria-label="`${label || 'JSON'} viewer`" @click.self="enlarged = false">
      <section class="payload-modal-card">
        <header class="payload-modal-header">
          <div>
            <div class="payload-modal-kicker">JSON payload</div>
            <h2>{{ label || 'Payload' }}</h2>
            <span>{{ formattedPayload.length.toLocaleString() }} chars · {{ formattedPayload.split('\n').length }} lines</span>
          </div>
          <div class="payload-modal-actions">
            <button type="button" class="payload-action payload-action--strong" @click="copyPayload">
              <span>{{ copied ? 'Copied' : 'Copy JSON' }}</span>
            </button>
            <button type="button" class="payload-close" aria-label="Close JSON viewer" @click="enlarged = false">×</button>
          </div>
        </header>
        <pre class="payload-modal-content"><code v-html="fullHighlightedPayload"></code></pre>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.payload-viewer {
  min-width: 0;
  overflow: hidden;
  border: 1px solid var(--border-subtle);
  border-radius: 9px;
  background: color-mix(in srgb, var(--bg-primary) 92%, var(--bg-secondary));
}
.payload-header {
  min-height: 34px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 10px;
  border-bottom: 1px solid var(--border-subtle);
  background: var(--bg-secondary);
}
.payload-label {
  color: var(--text-tertiary);
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.payload-language {
  padding: 1px 5px;
  border: 1px solid var(--border-subtle);
  border-radius: 4px;
  color: var(--text-secondary);
  font-family: var(--font-mono);
  font-size: 9px;
  font-weight: 600;
}
.payload-meta {
  margin-left: auto;
  color: var(--text-tertiary);
  font-family: var(--font-mono);
  font-size: 9px;
}
.payload-actions { margin-left: auto; display: inline-flex; align-items: center; gap: 4px; }
.payload-action {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-height: 25px;
  padding: 4px 7px;
  border: 1px solid transparent;
  border-radius: 5px;
  background: transparent;
  color: var(--text-tertiary);
  font-family: var(--font-mono);
  font-size: 9px;
  cursor: pointer;
}
.payload-action svg { width: 13px; height: 13px; }
.payload-action:hover { border-color: var(--border-subtle); background: var(--bg-hover); color: var(--text-primary); }
.payload-action:focus-visible, .payload-close:focus-visible { outline: 2px solid var(--text-accent); outline-offset: 1px; }
.payload-content {
  max-height: 420px;
  margin: 0;
  overflow-y: auto;
  padding: 12px 14px;
  color: var(--text-secondary);
  font-family: var(--font-mono);
  font-size: 11px;
  line-height: 1.65;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}
.payload-content code { font: inherit; }
.payload-content :deep(.hljs-attr) { color: var(--text-accent); }
.payload-content :deep(.hljs-string) { color: var(--color-success, #22c55e); }
.payload-content :deep(.hljs-number),
.payload-content :deep(.hljs-literal) { color: var(--color-warning, #d97706); }
.payload-content :deep(.hljs-punctuation) { color: var(--text-tertiary); }
.payload-toggle {
  width: 100%;
  min-height: 36px;
  padding: 7px 10px;
  border: 0;
  border-top: 1px solid var(--border-subtle);
  background: var(--bg-secondary);
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 500;
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
.payload-modal { position: fixed; z-index: 10050; inset: 0; display: grid; place-items: center; padding: 28px; background: rgba(8, 10, 14, .64); backdrop-filter: blur(4px); }
.payload-modal-card { display: flex; flex-direction: column; width: min(1100px, 94vw); height: min(820px, 90vh); overflow: hidden; border: 1px solid var(--border-subtle); border-radius: 12px; background: var(--dialog-surface); box-shadow: 0 24px 80px rgba(0, 0, 0, .35); }
.payload-modal-header { display: flex; align-items: center; justify-content: space-between; gap: 20px; padding: 16px 18px; border-bottom: 1px solid var(--border-subtle); background: var(--bg-secondary); }
.payload-modal-kicker { color: var(--text-accent); font-family: var(--font-mono); font-size: 9px; font-weight: 700; letter-spacing: .1em; text-transform: uppercase; }
.payload-modal-header h2 { margin: 3px 0 3px; color: var(--text-primary); font-size: 15px; font-weight: 600; }
.payload-modal-header span { color: var(--text-tertiary); font-family: var(--font-mono); font-size: 10px; }
.payload-modal-actions { display: inline-flex; align-items: center; gap: 8px; }
.payload-action--strong { border-color: var(--border-subtle); background: var(--bg-primary); color: var(--text-secondary); font-family: inherit; font-size: 11px; }
.payload-close { width: 30px; height: 30px; border: 1px solid transparent; border-radius: 6px; background: transparent; color: var(--text-tertiary); font-size: 22px; line-height: 1; cursor: pointer; }
.payload-close:hover { background: var(--bg-hover); color: var(--text-primary); }
.payload-modal-content { flex: 1; min-height: 0; margin: 0; overflow: auto; padding: 20px 22px 32px; background: color-mix(in srgb, var(--bg-primary) 94%, #0b1220); color: var(--text-secondary); font-family: var(--font-mono); font-size: 12px; line-height: 1.7; tab-size: 2; white-space: pre; }
.payload-modal-content code { font: inherit; }
.payload-modal-content :deep(.hljs-attr) { color: var(--text-accent); }
.payload-modal-content :deep(.hljs-string) { color: var(--color-success, #22c55e); }
.payload-modal-content :deep(.hljs-number), .payload-modal-content :deep(.hljs-literal) { color: var(--color-warning, #d97706); }
@media (max-width: 640px) {
  .payload-action span { display: none; }
  .payload-modal { padding: 10px; }
  .payload-modal-card { width: 100%; height: 94vh; }
  .payload-modal-header { padding: 13px; }
  .payload-modal-content { padding: 14px; font-size: 11px; }
}
</style>
