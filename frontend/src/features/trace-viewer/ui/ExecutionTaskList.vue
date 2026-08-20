<script setup>
import ExecutionTreeRow from './ExecutionTreeRow.vue'

const props = defineProps({
  tasks: { type: Array, default: () => [] },
  expandedTasks: { type: Object, required: true },
  selectedLoopId: { type: String, default: null },
  loopLoadState: { type: Function, default: () => 'idle' },
  subagentsForLoop: { type: Function, default: () => [] },
  subagentLoadState: { type: Function, default: () => 'idle' },
})

const emit = defineEmits(['toggle-task', 'select-loop', 'open-subagent'])

function causalityLabel(loops, index) {
  if (index === 0) return null
  const names = loops[index - 1]?.tool_names || []
  if (!names.length) return null
  const display = names.slice(0, 3).join(', ')
  return names.length > 3 ? `Receives results from: ${display} +${names.length - 3}` : `Receives results from: ${display}`
}

function loopSubagents(loop) {
  return props.subagentsForLoop(loop) || []
}
</script>

<template>
  <ExecutionTreeRow
    v-for="task in tasks"
    :key="task.id"
    :node="task"
    node-type="task"
    :depth="0"
    :expanded="expandedTasks.has(task.id)"
    @toggle="emit('toggle-task', task.id)"
    @open-subagent="emit('open-subagent', $event)"
  >
    <template v-for="(loop, loopIndex) in task.loops" :key="loop.id">
      <div v-if="causalityLabel(task.loops, loopIndex)" class="causality-label">
        <span class="causality-arrow" aria-hidden="true">&#x2190;</span>
        {{ causalityLabel(task.loops, loopIndex) }}
      </div>
      <ExecutionTreeRow
        :node="loop"
        node-type="loop"
        :depth="1"
        :selected="selectedLoopId === loop.id"
        :load-state="loopLoadState(loop.id)"
        @select-loop="emit('select-loop', $event)"
      >
        <ExecutionTreeRow
          v-for="subagent in loopSubagents(loop)"
          :key="subagent.tool_use_id || subagent.span_id"
          :node="subagent"
          node-type="subagent"
          :depth="2"
          :load-state="subagentLoadState(subagent)"
          @open-subagent="emit('open-subagent', $event)"
        />
      </ExecutionTreeRow>
    </template>
  </ExecutionTreeRow>
</template>

<style scoped>
.causality-label { display: flex; align-items: center; gap: 5px; padding: 2px 10px 2px 52px; color: var(--text-tertiary); font-size: 10px; font-style: italic; }
.causality-arrow { color: var(--text-accent); font-style: normal; font-weight: 600; }
</style>
