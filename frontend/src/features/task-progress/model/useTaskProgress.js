import { computed } from 'vue'
import { useSession } from '@entities/session'

const TASK_TOOL_NAMES = new Set(['TaskCreate', 'TaskUpdate', 'TaskList', 'TaskGet'])

function normalizePlanStatus(status) {
  if (status === 'running') return 'in_progress'
  if (status === 'done') return 'completed'
  return status || 'pending'
}

function toTaskId(value) {
  if (value == null || value === '') return ''
  return String(value)
}

function parseToolResultContent(content) {
  if (content == null) return null
  if (Array.isArray(content) || typeof content === 'object') return content
  if (typeof content === 'number') return content
  if (typeof content !== 'string') return null

  const trimmed = content.trim()
  if (!trimmed) return null

  try {
    return JSON.parse(trimmed)
  } catch {
    return null
  }
}

function normalizeTaskRecord(rawTask, fallback = {}) {
  if (!rawTask || typeof rawTask !== 'object' || Array.isArray(rawTask)) return null

  const id = toTaskId(rawTask.taskId ?? rawTask.task_id ?? rawTask.id ?? fallback.id)
  if (!id) return null

  return {
    id,
    subject: rawTask.subject || rawTask.content || fallback.subject || '',
    status: normalizePlanStatus(rawTask.status || fallback.status || 'pending'),
    description: rawTask.description || fallback.description || '',
    activeForm: rawTask.activeForm || rawTask.active_form || fallback.activeForm || '',
  }
}

function extractTaskRecords(payload) {
  if (Array.isArray(payload)) return payload
  if (payload && typeof payload === 'object') {
    if (Array.isArray(payload.tasks)) return payload.tasks
    if (Array.isArray(payload.items)) return payload.items
    if (payload.taskId != null || payload.task_id != null || payload.id != null) return [payload]
  }
  return []
}

function buildPendingTask(input = {}, tempId) {
  return {
    id: tempId,
    subject: input.subject || input.content || '',
    status: normalizePlanStatus(input.status || 'pending'),
    description: input.description || '',
    activeForm: input.activeForm || '',
  }
}

function upsertTask(tasks, order, taskId, patch) {
  const prev = tasks[taskId] || {
    id: taskId,
    subject: '',
    status: 'pending',
    description: '',
    activeForm: '',
  }
  tasks[taskId] = {
    ...prev,
    ...patch,
    id: taskId,
    status: normalizePlanStatus((patch && patch.status) || prev.status),
  }
  if (!order.includes(taskId)) order.push(taskId)
}

function replaceTaskId(tasks, order, oldId, newId, patch = {}) {
  const prev = tasks[oldId] || {}
  delete tasks[oldId]
  const index = order.indexOf(oldId)
  if (index !== -1) order.splice(index, 1, newId)
  upsertTask(tasks, order, newId, { ...prev, ...patch, id: newId })
}

function buildTodoWriteTasks(messages, sessionRunning) {
  let latestTodos = null

  for (const msg of messages) {
    if (msg.type !== 'assistant' || !msg.content?.blocks) continue
    for (const block of msg.content.blocks) {
      if (block.type === 'tool_use' && block.name === 'TodoWrite' && block.input?.todos) {
        latestTodos = block.input.todos
      }
    }
  }

  if (!latestTodos) return []

  return latestTodos.map((todo, i) => {
    let todoStatus = normalizePlanStatus(todo.status || 'pending')
    if (!sessionRunning && todoStatus === 'in_progress') {
      todoStatus = 'completed'
    }
    return {
      id: `plan-${i}`,
      subject: todo.subject || todo.content || '',
      status: todoStatus,
      description: todo.description || '',
      activeForm: todo.activeForm || '',
    }
  })
}

export function useTaskProgress() {
  const { messages, status, runSteps } = useSession()

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
    const sessionRunning = status.value === 'running'
    if (!sessionRunning) {
      for (const t of all) {
        if (t.status === 'running') {
          t.status = 'completed'
          t.endTime = t.endTime || Date.now()
        }
      }
    }
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

  const planTasks = computed(() => {
    const sessionRunning = status.value === 'running'
    const fallbackTodos = buildTodoWriteTasks(messages.value, sessionRunning)

    let hasTaskToolActivity = false
    let tasks = {}
    let order = []
    const toolUseById = {}
    const pendingCreatesByUseId = {}

    for (const msg of messages.value) {
      if (msg.type === 'assistant' && msg.content?.blocks) {
        for (const block of msg.content.blocks) {
          if (block.type !== 'tool_use') continue

          if (TASK_TOOL_NAMES.has(block.name)) {
            hasTaskToolActivity = true
            if (block.id) toolUseById[block.id] = block
          }

          if (block.name === 'TaskCreate' && block.id) {
            const tempId = `pending:${block.id}`
            const pendingTask = buildPendingTask(block.input || {}, tempId)
            pendingCreatesByUseId[block.id] = pendingTask
            upsertTask(tasks, order, tempId, pendingTask)
          }

          if (block.name === 'TaskUpdate') {
            const taskId = toTaskId(block.input?.taskId ?? block.input?.task_id)
            if (!taskId) continue
            upsertTask(tasks, order, taskId, {
              subject: block.input?.subject,
              status: block.input?.status,
              description: block.input?.description,
              activeForm: block.input?.activeForm,
            })
          }
        }
      }

      if (msg.type === 'tool_result' && msg.content?.results) {
        for (const result of msg.content.results) {
          const toolUse = toolUseById[result.tool_use_id]
          if (!toolUse || !TASK_TOOL_NAMES.has(toolUse.name)) continue

          hasTaskToolActivity = true
          const parsed = parseToolResultContent(result.content)

          if (toolUse.name === 'TaskCreate') {
            const pendingTask = pendingCreatesByUseId[result.tool_use_id]
            let createdTask = normalizeTaskRecord(parsed, pendingTask)
            if (!createdTask && pendingTask) {
              const createdTaskId = toTaskId(parsed)
              if (createdTaskId) {
                createdTask = { ...pendingTask, id: createdTaskId }
              }
            }
            if (pendingTask && createdTask) {
              replaceTaskId(tasks, order, pendingTask.id, createdTask.id, createdTask)
            }
            continue
          }

          if (toolUse.name === 'TaskList') {
            const listedTasks = extractTaskRecords(parsed)
              .map(item => normalizeTaskRecord(item))
              .filter(Boolean)

            if (listedTasks.length > 0) {
              const nextTasks = {}
              const nextOrder = []
              for (const task of listedTasks) {
                nextTasks[task.id] = { ...(tasks[task.id] || {}), ...task }
                nextOrder.push(task.id)
              }
              for (const existingId of order) {
                if (!nextTasks[existingId] && tasks[existingId]) {
                  nextTasks[existingId] = tasks[existingId]
                  nextOrder.push(existingId)
                }
              }
              tasks = nextTasks
              order = nextOrder
            }
            continue
          }

          if (toolUse.name === 'TaskGet') {
            const fetchedTask = normalizeTaskRecord(parsed)
            if (fetchedTask) {
              upsertTask(tasks, order, fetchedTask.id, fetchedTask)
            }
          }
        }
      }
    }

    let finalTasks = hasTaskToolActivity
      ? order.map(id => tasks[id]).filter(Boolean)
      : fallbackTodos

    if (!hasTaskToolActivity && finalTasks.length === 0) return []
    if (hasTaskToolActivity && finalTasks.length === 0) finalTasks = fallbackTodos

    if (!sessionRunning) {
      finalTasks = finalTasks.map(task => (
        task.status === 'in_progress'
          ? { ...task, status: 'completed' }
          : task
      ))
    }

    return finalTasks
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

  const timelineSteps = computed(() => runSteps.value.map(step => ({
    ...step,
    startedAt: step.started_time ? new Date(step.started_time).getTime() : Date.now(),
  })))

  const timelineCounts = computed(() => {
    const counts = { running: 0, completed: 0, failed: 0, total: 0 }
    for (const step of timelineSteps.value) {
      counts.total++
      if (step.status === 'running') counts.running++
      else if (step.status === 'completed') counts.completed++
      else if (step.status === 'failed') counts.failed++
    }
    return counts
  })

  const hasTimelineSteps = computed(() => timelineSteps.value.length > 0)

  return {
    allTasks,
    taskCounts,
    hasActiveTasks,
    planTasks,
    planTaskCounts,
    hasPlanTasks,
    timelineSteps,
    timelineCounts,
    hasTimelineSteps,
  }
}
