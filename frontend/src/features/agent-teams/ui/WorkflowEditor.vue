<script setup>
import { computed, onBeforeUnmount } from 'vue'
import WorkflowNode from './WorkflowNode.vue'

const props = defineProps({
  mode: { type: String, default: 'delegation' },
  steps: { type: Array, default: () => [] },
  tasks: { type: Array, default: () => [] },
  editable: { type: Boolean, default: false },
})

const emit = defineEmits(['reorder'])

const NODE_W = 140
const NODE_H = 56
const GAP_Y = 24
const PAD = 20

const nodes = computed(() => {
  const items = props.steps.map((step, i) => {
    const matching = props.tasks.filter(t => t.target_role === step.role)
    const task = matching.at(-1)
    return {
      ...step,
      index: i,
      status: task?.status || '',
      x: PAD,
      y: PAD + i * (NODE_H + GAP_Y),
    }
  })
  return items
})

const svgHeight = computed(() => {
  const count = props.steps.length || 1
  return PAD * 2 + count * NODE_H + (count - 1) * GAP_Y
})

const svgWidth = computed(() => PAD * 2 + NODE_W)

const connections = computed(() => {
  if (props.mode !== 'delegation') return []
  const lines = []
  for (let i = 0; i < nodes.value.length - 1; i++) {
    const from = nodes.value[i]
    const to = nodes.value[i + 1]
    lines.push({
      x1: from.x + NODE_W / 2,
      y1: from.y + NODE_H,
      x2: to.x + NODE_W / 2,
      y2: to.y,
    })
  }
  return lines
})

let dragIndex = -1
let dragStartY = 0

function onDragStart(index, e) {
  if (!props.editable) return
  dragIndex = index
  dragStartY = e.clientY
  document.addEventListener('mousemove', onDragMove)
  document.addEventListener('mouseup', onDragEnd)
}

function onDragMove(e) {
  if (dragIndex < 0) return
  const dy = e.clientY - dragStartY
  const stepHeight = NODE_H + GAP_Y
  const steps = Math.round(dy / stepHeight)
  if (steps !== 0) {
    const newIndex = Math.max(0, Math.min(props.steps.length - 1, dragIndex + steps))
    if (newIndex !== dragIndex) {
      emit('reorder', { from: dragIndex, to: newIndex })
      dragIndex = newIndex
      dragStartY = e.clientY
    }
  }
}

function onDragEnd() {
  dragIndex = -1
  document.removeEventListener('mousemove', onDragMove)
  document.removeEventListener('mouseup', onDragEnd)
}

onBeforeUnmount(onDragEnd)
</script>

<template>
  <div class="workflow-editor">
    <svg :width="svgWidth" :height="svgHeight" class="workflow-svg">
      <!-- Connection lines -->
      <line
        v-for="(conn, i) in connections"
        :key="'conn-' + i"
        :x1="conn.x1"
        :y1="conn.y1"
        :x2="conn.x2"
        :y2="conn.y2"
        class="conn-line"
      />
      <!-- Arrow heads -->
      <polygon
        v-for="(conn, i) in connections"
        :key="'arrow-' + i"
        :points="`${conn.x2 - 4},${conn.y2 - 6} ${conn.x2 + 4},${conn.y2 - 6} ${conn.x2},${conn.y2}`"
        class="conn-arrow"
      />
      <!-- Nodes -->
      <WorkflowNode
        v-for="node in nodes"
        :key="node.role"
        :role="node.role"
        :label="node.role_label || node.role"
        :status="node.status"
        :x="node.x"
        :y="node.y"
        :width="NODE_W"
        :height="NODE_H"
        :editable="editable"
        @mousedown="onDragStart(node.index, $event)"
      />
    </svg>
    <div v-if="steps.length === 0" class="empty-text">No steps configured</div>
  </div>
</template>

<style scoped>
.workflow-editor {
  overflow: auto;
}

.workflow-svg {
  display: block;
}

.conn-line {
  stroke: var(--border);
  stroke-width: 1.5;
  stroke-dasharray: 4 3;
}

.conn-arrow {
  fill: var(--border);
}

.empty-text {
  font-size: 12px;
  color: var(--text-muted);
  padding: 12px 0;
}
</style>
