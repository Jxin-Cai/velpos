<script setup>
import { computed } from 'vue'
import SpanPayloadViewer from './SpanPayloadViewer.vue'

const props = defineProps({
  loopId: { type: String, default: null },
  detail: { type: Object, default: null },
  loadState: { type: String, default: 'idle' },
  provenance: { type: Object, default: null },
})

const events = computed(() => props.detail?.items || [])
const total = computed(() => props.detail?.total || 0)
const hasMore = computed(() => props.detail?.next_cursor != null)

const toolCalls = computed(() => events.value.filter(e => e.type === 'tool_use' || e.type === 'tool_result'))
const modelInputs = computed(() => events.value.filter(e => e.type === 'model_input' || e.type === 'user_message'))
const modelOutputs = computed(() => events.value.filter(e => e.type === 'assistant_message' || e.type === 'model_output'))

const isReconstructed = computed(() => props.provenance?.reconstructed_from_transcript)

function formatContent(content) {
  if (!content) return ''
  if (typeof content === 'string') return content
  try {
    return JSON.stringify(content, null, 2)
  } catch {
    return String(content)
  }
}

function eventIcon(type) {
  if (type === 'tool_use') return 'tool-req'
  if (type === 'tool_result') return 'tool-res'
  if (type === 'assistant_message' || type === 'model_output') return 'output'
  if (type === 'model_input' || type === 'user_message') return 'input'
  return 'generic'
}

function eventLabel(type) {
  const labels = {
    tool_use: 'Tool call',
    tool_result: 'Tool result',
    assistant_message: 'Model output',
    model_output: 'Model output',
    model_input: 'Model input',
    user_message: 'User input',
  }
  return labels[type] || type
}
</script>

<template>
  <div class="exec-detail">
    <div v-if="loadState === 'loading'" class="detail-loading">
      <span class="detail-spinner" aria-hidden="true"></span>
      <span>Loading loop detail...</span>
    </div>

    <div v-else-if="loadState === 'error'" class="detail-error">
      <span>Failed to load loop detail</span>
      <span v-if="detail?.error" class="detail-error-msg">{{ detail.error }}</span>
    </div>

    <div v-else-if="!loopId" class="detail-empty">
      <p>Select a loop to view execution details</p>
    </div>

    <template v-else>
      <div v-if="isReconstructed" class="detail-provenance">
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
          <circle cx="8" cy="8" r="6.25"/><path d="M8 5v3.5M8 11h.01"/>
        </svg>
        <span>Reconstructed from transcript</span>
        <span v-if="provenance?.completeness && provenance.completeness !== 'complete'" class="provenance-tag">
          {{ provenance.completeness }}
        </span>
      </div>

      <div class="detail-summary">
        <span class="summary-item">{{ total }} events</span>
        <span class="summary-item">{{ toolCalls.length }} tool calls</span>
        <span v-if="hasMore" class="summary-item summary-more">More available</span>
      </div>

      <div class="detail-events">
        <div v-for="(event, idx) in events" :key="idx" class="event-item" :class="`event-item--${eventIcon(event.type)}`">
          <div class="event-header">
            <span class="event-type-badge" :class="`badge--${eventIcon(event.type)}`">
              {{ eventLabel(event.type) }}
            </span>
            <span v-if="event.tool_name" class="event-tool-name">{{ event.tool_name }}</span>
            <span v-if="event.is_error" class="event-error-flag">error</span>
          </div>
          <div v-if="event.content" class="event-content">
            <SpanPayloadViewer
              :payload="formatContent(event.content)"
              :label="event.tool_name || eventLabel(event.type)"
            />
          </div>
        </div>
      </div>

      <div v-if="events.length === 0 && loadState === 'loaded'" class="detail-empty">
        <p>No events in this loop</p>
      </div>
    </template>
  </div>
</template>

<style scoped>
.exec-detail {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 12px;
  min-height: 120px;
}
.detail-loading, .detail-error, .detail-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 100px;
  color: var(--text-tertiary);
  font-size: 12px;
}
.detail-error { color: var(--color-error, #ef4444); }
.detail-error-msg { font-size: 11px; color: var(--text-tertiary); }
.detail-spinner { width: 14px; height: 14px; border: 1.5px solid var(--border); border-top-color: var(--text-secondary); border-radius: 50%; animation: detail-spin 700ms linear infinite; }
.detail-provenance {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border: 1px solid color-mix(in srgb, var(--color-warning, #f59e0b) 40%, var(--border-subtle));
  border-radius: 6px;
  background: color-mix(in srgb, var(--color-warning, #f59e0b) 6%, var(--bg-secondary));
  color: var(--text-secondary);
  font-size: 11px;
}
.provenance-tag {
  padding: 1px 5px;
  border-radius: 3px;
  background: var(--bg-tertiary);
  font-family: var(--font-mono);
  font-size: 9px;
  text-transform: uppercase;
}
.detail-summary {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 2px;
}
.summary-item { color: var(--text-tertiary); font-size: 11px; font-family: var(--font-mono); }
.summary-more { color: var(--text-accent); }
.detail-events { display: flex; flex-direction: column; gap: 6px; }
.event-item {
  padding: 8px 10px;
  border: 1px solid var(--border-subtle);
  border-radius: 7px;
  background: var(--bg-primary);
}
.event-item--tool-req { border-left: 2px solid var(--text-secondary); }
.event-item--tool-res { border-left: 2px solid var(--color-success, #22c55e); }
.event-item--output { border-left: 2px solid var(--text-accent); }
.event-item--input { border-left: 2px solid var(--text-tertiary); }
.event-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.event-type-badge {
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 9px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  background: var(--bg-secondary);
  color: var(--text-tertiary);
}
.badge--tool-req { color: var(--text-secondary); }
.badge--tool-res { color: var(--color-success, #22c55e); }
.badge--output { color: var(--text-accent); }
.event-tool-name { font-family: var(--font-mono); font-size: 11px; color: var(--text-secondary); font-weight: 500; }
.event-error-flag { padding: 1px 5px; border-radius: 3px; background: color-mix(in srgb, var(--color-error, #ef4444) 12%, transparent); color: var(--color-error, #ef4444); font-size: 9px; font-weight: 600; }
.event-content { margin-top: 4px; }
@keyframes detail-spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .detail-spinner { animation: none; } }
</style>
