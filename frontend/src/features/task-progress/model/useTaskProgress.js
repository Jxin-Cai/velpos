import { computed } from 'vue'
import { useSession } from '@entities/session'

export function useTaskProgress() {
  const { messages } = useSession()

  const allTasks = computed(() => {
    const tasks = {}
    const now = Date.now()

    for (const msg of messages.value) {
      if (msg.type !== 'system' || !msg.content) continue
      const { subtype, task_id, description, status: taskStatus, summary, last_tool_name } = msg.content
      if (!task_id) continue

      if (subtype === 'task_started') {
        tasks[task_id] = {
          task_id,
          description: description || '',
          status: 'running',
          startTime: msg.timestamp || now,
          endTime: null,
          last_tool_name: '',
          summary: '',
        }
      } else if (subtype === 'task_progress') {
        if (tasks[task_id]) {
          if (description) tasks[task_id].description = description
          if (last_tool_name) tasks[task_id].last_tool_name = last_tool_name
        } else {
          tasks[task_id] = {
            task_id,
            description: description || '',
            status: 'running',
            startTime: now,
            endTime: null,
            last_tool_name: last_tool_name || '',
            summary: '',
          }
        }
      } else if (subtype === 'task_notification') {
        if (tasks[task_id]) {
          tasks[task_id].status = taskStatus || 'completed'
          tasks[task_id].summary = summary || ''
          tasks[task_id].endTime = now
        }
      }
    }

    const all = Object.values(tasks)
    // Running first (oldest first), then non-running (newest first)
    const running = all.filter(t => t.status === 'running').sort((a, b) => a.startTime - b.startTime)
    const done = all.filter(t => t.status !== 'running').sort((a, b) => (b.endTime || 0) - (a.endTime || 0))
    return [...running, ...done]
  })

  const taskCounts = computed(() => {
    const counts = { running: 0, completed: 0, failed: 0, total: 0 }
    for (const t of allTasks.value) {
      counts.total++
      if (t.status === 'running') counts.running++
      else if (t.status === 'completed') counts.completed++
      else counts.failed++
    }
    return counts
  })

  const hasActiveTasks = computed(() => taskCounts.value.running > 0)

  // ── Plan tasks from TodoWrite tool calls ──────────────────

  const planTasks = computed(() => {
    let latestTodos = null

    for (const msg of messages.value) {
      if (msg.type !== 'assistant' || !msg.content?.blocks) continue
      for (const block of msg.content.blocks) {
        if (block.type === 'tool_use' && block.name === 'TodoWrite' && block.input?.todos) {
          // TodoWrite sends the full current list each time — last call wins
          latestTodos = block.input.todos
        }
      }
    }

    if (!latestTodos) return []

    return latestTodos.map((todo, i) => ({
      id: `plan-${i}`,
      subject: todo.subject || todo.content || '',
      status: todo.status || 'pending',
      description: todo.description || '',
      activeForm: todo.activeForm || '',
    }))
  })

  const planTaskCounts = computed(() => {
    const counts = { pending: 0, in_progress: 0, completed: 0, total: 0 }
    for (const t of planTasks.value) {
      counts.total++
      if (t.status === 'in_progress') counts.in_progress++
      else if (t.status === 'completed') counts.completed++
      else counts.pending++
    }
    return counts
  })

  const hasPlanTasks = computed(() => planTasks.value.length > 0)

  return { allTasks, taskCounts, hasActiveTasks, planTasks, planTaskCounts, hasPlanTasks }
}
