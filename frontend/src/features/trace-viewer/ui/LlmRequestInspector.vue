<script setup>
import { computed, ref, watch } from 'vue'
import SpanPayloadViewer from './SpanPayloadViewer.vue'

const props = defineProps({
  summary: { type: Object, default: null },
  state: { type: Object, default: null },
  loadDetail: { type: Function, default: async () => {} },
})

const open = ref(false)

const detail = computed(() => props.state?.detail || null)
const loading = computed(() => Boolean(props.state?.loading))
const error = computed(() => props.state?.error || '')

const CHANGE_LABELS = Object.freeze({
  initial: 'First request',
  unchanged: 'Same envelope',
  system: 'System prompt changed',
  tools: 'Tool catalog changed',
  system_and_tools: 'System prompt and tools changed',
})

const changeLabel = computed(() => CHANGE_LABELS[props.summary?.change] || props.summary?.change || '')
const isChanged = computed(() => ['system', 'tools', 'system_and_tools'].includes(props.summary?.change))

const toolList = computed(() => detail.value?.tools || [])
const messages = computed(() => detail.value?.messages || [])

function formatChars(count) {
  const value = Number(count) || 0
  if (value >= 1000000) return `${(value / 1000000).toFixed(1)}M`
  if (value >= 1000) return `${(value / 1000).toFixed(1)}k`
  return String(value)
}

watch(open, isOpen => {
  if (isOpen && !detail.value && !loading.value && props.summary?.event_id) {
    props.loadDetail(props.summary.event_id)
  }
})
</script>

<template>
  <details v-if="summary" class="request-card" :open="open" @toggle="open = $event.target.open">
    <summary class="request-summary">
      <span class="request-label">Request</span>
      <span class="request-title">{{ summary.model || 'Provider request' }}</span>
      <span class="request-chips">
        <span class="chip">system {{ formatChars(summary.system_char_count) }} chars</span>
        <span class="chip">{{ summary.message_count }} messages</span>
        <span class="chip">{{ summary.tool_count }} tools</span>
        <span v-if="isChanged" class="chip chip--changed">{{ changeLabel }}</span>
      </span>
    </summary>

    <div class="request-body">
      <p v-if="loading" class="request-note">Loading request envelope…</p>
      <p v-else-if="error" class="request-note request-note--error">{{ error }}</p>

      <template v-else-if="detail">
        <section class="request-section">
          <h4>System prompt <span>{{ formatChars(detail.system_char_count) }} chars</span></h4>
          <pre v-if="detail.system" class="request-text">{{ detail.system }}</pre>
          <p v-else class="request-note">This request carried no system prompt.</p>
        </section>

        <section class="request-section">
          <h4>Messages <span>{{ detail.message_count }} entries · {{ formatChars(detail.message_char_count) }} chars</span></h4>
          <SpanPayloadViewer v-if="messages.length" :payload="messages" label="messages" />
          <p v-else class="request-note">This request carried no message history.</p>
        </section>

        <section class="request-section">
          <h4>Tool definitions <span>{{ toolList.length }} tools</span></h4>
          <ul v-if="toolList.length" class="tool-list">
            <li v-for="tool in toolList" :key="tool.name">
              <details class="tool-item">
                <summary>
                  <span class="tool-name">{{ tool.name }}</span>
                  <span v-if="tool.description" class="tool-description">{{ tool.description }}</span>
                </summary>
                <SpanPayloadViewer :payload="tool.input_schema" :label="`${tool.name} schema`" />
              </details>
            </li>
          </ul>
          <p v-else class="request-note">This request exposed no tools.</p>
        </section>
      </template>
    </div>
  </details>
</template>

<style scoped>
.request-card {
  border: 1px solid var(--border-subtle);
  border-radius: 9px;
  background: var(--bg-primary);
}
.request-summary {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 9px 11px;
  cursor: pointer;
  list-style: none;
}
.request-summary::-webkit-details-marker { display: none; }
.request-label {
  padding: 1px 6px;
  border: 1px solid var(--border-subtle);
  border-radius: 4px;
  color: var(--text-tertiary);
  font-family: var(--font-mono);
  font-size: 9px;
  font-weight: 700;
  letter-spacing: .07em;
  text-transform: uppercase;
}
.request-title {
  color: var(--text-primary);
  font-size: 12px;
  font-weight: 600;
}
.request-chips { margin-left: auto; display: inline-flex; flex-wrap: wrap; gap: 5px; }
.chip {
  padding: 1px 6px;
  border: 1px solid var(--border-subtle);
  border-radius: 4px;
  color: var(--text-tertiary);
  font-family: var(--font-mono);
  font-size: 9px;
}
.chip--changed {
  border-color: color-mix(in srgb, var(--color-warning, #d97706) 45%, transparent);
  color: var(--color-warning, #d97706);
}
.request-body {
  display: flex;
  flex-direction: column;
  gap: 13px;
  padding: 4px 11px 12px;
  border-top: 1px solid var(--border-subtle);
}
.request-section { display: flex; flex-direction: column; gap: 7px; padding-top: 9px; }
.request-section h4 {
  display: flex;
  align-items: baseline;
  gap: 7px;
  margin: 0;
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 600;
}
.request-section h4 span {
  color: var(--text-tertiary);
  font-family: var(--font-mono);
  font-size: 9px;
  font-weight: 400;
}
.request-text {
  max-height: 320px;
  margin: 0;
  overflow: auto;
  padding: 10px 12px;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  background: color-mix(in srgb, var(--bg-primary) 92%, var(--bg-secondary));
  color: var(--text-secondary);
  font-family: var(--font-mono);
  font-size: 11px;
  line-height: 1.65;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.request-note { margin: 0; color: var(--text-tertiary); font-size: 11px; }
.request-note--error { color: var(--color-danger, #dc2626); }
.tool-list { display: flex; flex-direction: column; gap: 5px; margin: 0; padding: 0; list-style: none; }
.tool-item {
  border: 1px solid var(--border-subtle);
  border-radius: 7px;
  background: color-mix(in srgb, var(--bg-primary) 92%, var(--bg-secondary));
}
.tool-item > summary {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 7px 10px;
  cursor: pointer;
}
.tool-name { color: var(--text-primary); font-family: var(--font-mono); font-size: 11px; font-weight: 600; }
.tool-description {
  overflow: hidden;
  color: var(--text-tertiary);
  font-size: 10px;
  white-space: nowrap;
  text-overflow: ellipsis;
}
</style>
