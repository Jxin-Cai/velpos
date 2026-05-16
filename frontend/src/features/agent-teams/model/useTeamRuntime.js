import { ref, computed } from 'vue'
import { getTeamTimeline, getLinkedSessions } from '../api/teamApi'

const teamTasks = ref(new Map())
const workerSessionStates = ref(new Map())

function displayStatusFromTaskStatus(status) {
  if (['completed', 'failed', 'cancelled'].includes(status)) return status
  if (['running', 'waiting_for_help'].includes(status)) return 'running'
  return status || 'idle'
}

function setWorkerSessionState(sessionId, patch) {
  if (!sessionId) return
  const current = workerSessionStates.value.get(sessionId) || {}
  workerSessionStates.value = new Map(workerSessionStates.value.set(sessionId, { ...current, ...patch }))
}

export function useTeamRuntime() {
  function handleTeamEvent(event) {
    const data = event
    const coordSessionId = data.coordinator_session_id
    if (!coordSessionId) return

    const eventType = data.event
    const task = data.task

    if (!task) return

    const tasks = teamTasks.value.get(coordSessionId) || []

    if (eventType === 'team_task_created') {
      tasks.push(task)
    } else {
      const idx = tasks.findIndex(t => t.task_id === task.task_id)
      if (idx >= 0) {
        tasks[idx] = task
      } else {
        tasks.push(task)
      }
    }

    if (task.worker_session_id) {
      setWorkerSessionState(task.worker_session_id, {
        display_status: displayStatusFromTaskStatus(task.status),
        task_status: task.status,
        waiting_for_input: false,
      })
    }

    teamTasks.value = new Map(teamTasks.value.set(coordSessionId, [...tasks]))
  }

  function handleWorkerSessionEvent(event) {
    const sessionId = event?.session_id
    if (!sessionId) return

    if (event.event === 'session_waiting_for_input') {
      setWorkerSessionState(sessionId, {
        display_status: 'waiting_input',
        waiting_for_input: true,
        agent_state: event.agent_state || 'waiting_permission',
        interaction_type: event.interaction_type || '',
      })
    } else if (event.event === 'session_input_resolved') {
      setWorkerSessionState(sessionId, {
        display_status: 'running',
        waiting_for_input: false,
        agent_state: event.agent_state || 'streaming',
      })
    }
  }

  function getTasksForSession(sessionId) {
    return computed(() => teamTasks.value.get(sessionId) || [])
  }

  function getWorkerSessionState(sessionId) {
    return workerSessionStates.value.get(sessionId) || null
  }

  async function loadTimeline(projectId, sessionId) {
    try {
      const timeline = await getTeamTimeline(projectId, sessionId)
      teamTasks.value = new Map(teamTasks.value.set(sessionId, timeline))
      for (const task of timeline) {
        if (task.worker_session_id) {
          setWorkerSessionState(task.worker_session_id, {
            display_status: displayStatusFromTaskStatus(task.status),
            task_status: task.status,
          })
        }
      }
      return timeline
    } catch (e) {
      console.error('Failed to load team timeline:', e)
      return []
    }
  }

  async function loadLinkedSessions(projectId, sessionId) {
    try {
      const sessions = await getLinkedSessions(projectId, sessionId)
      for (const session of sessions) {
        setWorkerSessionState(session.session_id, {
          display_status: session.display_status || displayStatusFromTaskStatus(session.task_status),
          waiting_for_input: Boolean(session.waiting_for_input),
          agent_state: session.agent_state || '',
          task_status: session.task_status || '',
        })
      }
      return sessions
    } catch (e) {
      console.error('Failed to load linked sessions:', e)
      return []
    }
  }

  function clearSession(sessionId) {
    teamTasks.value.delete(sessionId)
    teamTasks.value = new Map(teamTasks.value)
  }

  return {
    teamTasks,
    workerSessionStates,
    displayStatusFromTaskStatus,
    handleTeamEvent,
    handleWorkerSessionEvent,
    getTasksForSession,
    getWorkerSessionState,
    loadTimeline,
    loadLinkedSessions,
    clearSession,
  }
}
