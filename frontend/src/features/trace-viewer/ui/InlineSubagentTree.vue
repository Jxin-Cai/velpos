<script setup>
import { reactive } from 'vue'
import ExecutionTreeRow from './ExecutionTreeRow.vue'
import SpanPayloadViewer from './SpanPayloadViewer.vue'

const props = defineProps({
  tree: { type: Object, required: true },
  agentSpanId: { type: String, required: true },
  getLoopDetail: { type: Function, required: true },
  getLoopLoadState: { type: Function, required: true },
  loadLoopDetail: { type: Function, required: true },
  loadMoreEvents: { type: Function, default: async () => {} },
})
const emit = defineEmits(['open-subagent'])

const expandedTasks = reactive(new Set())
const expandedLoops = reactive(new Set())

function toggleTask(taskId) {
  if (expandedTasks.has(taskId)) expandedTasks.delete(taskId)
  else expandedTasks.add(taskId)
}

function toggleLoop(loopId) {
  if (expandedLoops.has(loopId)) {
    expandedLoops.delete(loopId)
    return
  }

  expandedLoops.add(loopId)
  if (props.getLoopLoadState(loopId, props.agentSpanId) === 'idle') {
    props.loadLoopDetail(loopId, props.agentSpanId)
  }
}

function loopDetail(loopId) {
  return props.getLoopDetail(loopId, props.agentSpanId)
}

function loopState(loopId) {
  return props.getLoopLoadState(loopId, props.agentSpanId)
}

function subagentsForLoop(loop) {
  if (loop?.subagents?.length) return loop.subagents
  const ids = new Set(loop?.subagent_tool_use_ids || [])
  return (props.tree?.subagents || []).filter(subagent => ids.has(subagent.tool_use_id))
}

function pairedEvents(items = []) {
  const results = new Map(items.filter(item => item.type === 'tool_result').map(item => [item.tool_use_id, item]))
  const outputs = new Map(items.filter(item => item.type === 'model_output' && item.source_uuid).map(item => [item.source_uuid, item]))
  const inputs = new Set(items.filter(item => item.type === 'model_input' && item.source_uuid).map(item => item.source_uuid))
  return items.flatMap((event, index) => {
    if (event.type === 'tool_result') return []
    if (event.type === 'model_output' && event.source_uuid && inputs.has(event.source_uuid)) return []
    if (event.type === 'tool_use') {
      return [{ id: event.tool_use_id || index, label: event.tool_name || 'Tool call', input: event.content, output: results.get(event.tool_use_id)?.content }]
    }
    if (event.type === 'model_input') {
      return [{ id: event.source_uuid || index, label: 'Model turn', input: event.content, output: outputs.get(event.source_uuid)?.content }]
    }
    return [{ id: `${event.source_uuid || index}-${event.type}`, label: event.type, output: event.content }]
  })
}
</script>

<template>
  <div class="inline-subagent-container">
    <div class="inline-subagent-header">
      <span class="inline-agent-badge">
        <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true">
          <rect x="3" y="4" width="10" height="8" rx="2"/><path d="M8 2v2M6 8h.01M10 8h.01"/>
        </svg>
      </span>
      <span class="inline-agent-id">{{ tree.agent_id }}</span>
      <span class="inline-task-count">{{ tree.tasks?.length || 0 }} {{ tree.tasks?.length === 1 ? 'task' : 'tasks' }}</span>
    </div>

    <div class="inline-subagent-body">
      <!-- Context card: parent's prompt -->
      <div v-if="tree.request" class="subagent-context-card context-input">
        <div class="context-card-label">
          <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true"><path d="M3 8h9M8 4l4 4-4 4"/></svg>
          Input from parent
        </div>
        <SpanPayloadViewer :payload="tree.request" label="Parent prompt" />
      </div>

      <ExecutionTreeRow
        v-for="task in tree.tasks"
        :key="task.id"
        :node="task"
        node-type="task"
        :depth="0"
        :expanded="expandedTasks.has(task.id)"
        @toggle="toggleTask(task.id)"
      >
        <ExecutionTreeRow
          v-for="loop in task.loops"
          :key="loop.id"
          :node="loop"
          node-type="loop"
          :depth="1"
          :expanded="expandedLoops.has(loop.id)"
          :load-state="loopState(loop.id)"
          @select-loop="toggleLoop"
          @toggle="toggleLoop(loop.id)"
        >
          <ExecutionTreeRow
            v-for="subagent in subagentsForLoop(loop)"
            :key="subagent.tool_use_id"
            :node="subagent"
            node-type="subagent"
            :depth="2"
            @open-subagent="emit('open-subagent', $event)"
          />
          <div class="inline-step-detail">
            <div v-if="loopState(loop.id) === 'loading'" class="inline-state">Loading step...</div>
            <div v-else-if="loopState(loop.id) === 'error'" class="inline-state inline-state--error">
              {{ loopDetail(loop.id)?.error || 'Unable to load step' }}
            </div>
            <template v-else-if="loopDetail(loop.id)?.items?.length">
              <div v-for="event in pairedEvents(loopDetail(loop.id).items)" :key="event.id" class="inline-event">
                <div class="inline-event-header">{{ event.label }}</div>
                <div class="inline-event-payloads" :class="{ split: event.input != null && event.output != null }">
                  <SpanPayloadViewer v-if="event.input != null" :payload="event.input" label="Input" />
                  <SpanPayloadViewer v-if="event.output != null" :payload="event.output" label="Output" />
                </div>
              </div>
              <div v-if="loopDetail(loop.id).next_cursor != null || loopDetail(loop.id).moreError" class="inline-load-more">
                <button
                  type="button"
                  class="inline-load-more-btn"
                  :disabled="loopDetail(loop.id).loadingMore"
                  @click="loadMoreEvents(loop.id, agentSpanId)"
                >
                  {{ loopDetail(loop.id).loadingMore ? 'Loading more events…' : `Load more events (${loopDetail(loop.id).items.length} / ${loopDetail(loop.id).total})` }}
                </button>
                <span v-if="loopDetail(loop.id).moreError" class="inline-state--error">{{ loopDetail(loop.id).moreError }}</span>
              </div>
            </template>
            <div v-else-if="loopState(loop.id) === 'loaded'" class="inline-state">No recorded events</div>
          </div>
        </ExecutionTreeRow>
      </ExecutionTreeRow>

      <!-- Context card: return to parent -->
      <div v-if="tree.status && tree.status !== 'unknown'" class="subagent-context-card context-output">
        <div class="context-card-label">
          <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true"><path d="M13 8H4M8 4 4 8l4 4"/></svg>
          Returned to parent
        </div>
        <span class="context-status" :class="`context-status--${tree.status}`">{{ tree.status }}</span>
        <span v-if="tree.error_message" class="context-error">{{ tree.error_message }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.inline-subagent-container {
  margin-top: 8px;
  border: 1px solid color-mix(in srgb, var(--text-accent) 25%, var(--border-subtle));
  border-radius: 8px;
  background: color-mix(in srgb, var(--text-accent) 3%, var(--bg-primary));
  overflow: hidden;
}
.inline-subagent-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-bottom: 1px solid var(--border-subtle);
  background: color-mix(in srgb, var(--text-accent) 5%, var(--bg-secondary));
}
.inline-agent-badge {
  display: grid;
  place-items: center;
  width: 18px;
  height: 18px;
  border-radius: 4px;
  background: color-mix(in srgb, var(--text-accent) 15%, transparent);
  color: var(--text-accent);
}
.inline-agent-id {
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 500;
  color: var(--text-primary);
}
.inline-task-count {
  margin-left: auto;
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-tertiary);
}
.inline-subagent-body { padding: 4px; }
.subagent-context-card { margin: 6px 8px; padding: 8px 10px; border: 1px solid var(--border-subtle); border-radius: 7px; background: var(--bg-primary); }
.subagent-context-card.context-input { border-color: color-mix(in srgb, var(--text-accent) 28%, var(--border-subtle)); }
.subagent-context-card.context-output { border-color: color-mix(in srgb, var(--color-success, #22c55e) 28%, var(--border-subtle)); }
.context-card-label { display: flex; align-items: center; gap: 5px; margin-bottom: 6px; color: var(--text-tertiary); font-size: 10px; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; }
.context-card-label svg { color: var(--text-accent); }
.context-output .context-card-label svg { color: var(--color-success, #22c55e); }
.context-status { padding: 2px 7px; border-radius: 4px; font-size: 11px; font-weight: 500; background: var(--bg-secondary); color: var(--text-secondary); }
.context-status--completed { color: var(--color-success, #22c55e); }
.context-status--failed { color: var(--color-error, #ef4444); }
.context-error { display: block; margin-top: 5px; color: var(--color-error, #ef4444); font-size: 11px; white-space: pre-wrap; overflow-wrap: anywhere; }
.inline-step-detail {
  display: grid;
  gap: 6px;
  padding: 6px 8px 8px 40px;
}
.inline-state {
  padding: 6px 8px;
  font-size: 11px;
  color: var(--text-tertiary);
}
.inline-state--error { color: var(--color-error, #ef4444); }
.inline-load-more { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; padding: 4px 0; }
.inline-load-more-btn { min-height: 32px; padding: 6px 12px; border: 1px solid var(--border-subtle); border-radius: 7px; background: var(--bg-primary); color: var(--text-secondary); font-size: 11px; font-weight: 600; cursor: pointer; }
.inline-load-more-btn:hover:not(:disabled) { border-color: var(--text-accent); color: var(--text-primary); }
.inline-load-more-btn:focus-visible { outline: 2px solid var(--text-accent); outline-offset: 2px; }
.inline-load-more-btn:disabled { cursor: wait; opacity: .68; }
.inline-event { padding: 7px 8px; border-left: 2px solid var(--border-subtle); background: var(--bg-primary); }
.inline-event-header { margin-bottom: 5px; color: var(--text-secondary); font-family: var(--font-mono); font-size: 10px; }
.inline-event-payloads { display: grid; gap: 6px; }
.inline-event-payloads.split { grid-template-columns: repeat(2, minmax(0, 1fr)); }
@media (max-width: 760px) { .inline-event-payloads.split { grid-template-columns: 1fr; } }
</style>
