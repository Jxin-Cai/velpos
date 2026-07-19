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
})

const expandedTasks = reactive(new Set(
  (props.tree?.tasks || []).map(task => task.id),
))
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

function eventLabel(type) {
  const labels = {
    model_input: 'Model input',
    model_output: 'Model output',
    user_message: 'User message',
    assistant_message: 'Model output',
    tool_use: 'Tool call',
    tool_result: 'Tool result',
    subagent: 'Subagent call',
  }
  return labels[type] || type
}

function formatContent(content) {
  if (content == null) return ''
  if (typeof content === 'string') return content
  try {
    return JSON.stringify(content, null, 2)
  } catch {
    return String(content)
  }
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
      <span class="inline-task-count">{{ tree.tasks?.length || 0 }} tasks</span>
    </div>

    <div class="inline-subagent-body">
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
          @toggle="toggleLoop(loop.id)"
        >
          <div class="inline-step-detail">
            <div v-if="loopState(loop.id) === 'loading'" class="inline-state">Loading step...</div>
            <div v-else-if="loopState(loop.id) === 'error'" class="inline-state inline-state--error">
              {{ loopDetail(loop.id)?.error || 'Unable to load step' }}
            </div>
            <template v-else-if="loopDetail(loop.id)?.items?.length">
              <div
                v-for="(event, eventIndex) in loopDetail(loop.id).items"
                :key="event.source_uuid || `${loop.id}-${eventIndex}`"
                class="inline-event"
              >
                <div class="inline-event-header">
                  <span class="inline-event-type">{{ eventLabel(event.type) }}</span>
                  <span v-if="event.tool_name" class="inline-event-tool">{{ event.tool_name }}</span>
                  <span v-if="event.is_error" class="inline-event-error">error</span>
                </div>
                <SpanPayloadViewer
                  v-if="event.content != null"
                  :payload="formatContent(event.content)"
                  :label="event.tool_name || eventLabel(event.type)"
                />
              </div>
            </template>
            <div v-else-if="loopState(loop.id) === 'loaded'" class="inline-state">No recorded events</div>
          </div>
        </ExecutionTreeRow>
      </ExecutionTreeRow>
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
.inline-event {
  padding: 7px 8px;
  border-left: 2px solid var(--border-subtle);
  background: var(--bg-primary);
}
.inline-event-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}
.inline-event-type,
.inline-event-tool,
.inline-event-error {
  font-family: var(--font-mono);
  font-size: 10px;
}
.inline-event-type { color: var(--text-secondary); }
.inline-event-tool { color: var(--text-accent); }
.inline-event-error { margin-left: auto; color: var(--color-error, #ef4444); }
</style>
