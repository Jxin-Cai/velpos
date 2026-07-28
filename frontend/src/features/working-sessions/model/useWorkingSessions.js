import { ref, computed } from 'vue'

// Module-level singleton state
const workingSessions = ref(new Map())

export function useWorkingSessions() {
  const workingCount = computed(() => workingSessions.value.size)

  const workingList = computed(() =>
    Array.from(workingSessions.value.entries()).map(([sessionId, info]) => ({
      sessionId,
      ...info,
    }))
  )

  function markWorking(sessionId, { sessionName = '', projectName = '' } = {}) {
    const existing = workingSessions.value.get(sessionId)
    if (existing) return // already tracked
    const updated = new Map(workingSessions.value)
    updated.set(sessionId, { sessionName, projectName, startTime: Date.now() })
    workingSessions.value = updated
  }

  function markDone(sessionId) {
    if (!workingSessions.value.has(sessionId)) return
    const updated = new Map(workingSessions.value)
    updated.delete(sessionId)
    workingSessions.value = updated
  }

  function syncWorkingSessions(sessions = [], projects = []) {
    const projectNames = new Map(projects.map(project => [project.id, project.name || '']))
    const updated = new Map()

    for (const session of sessions) {
      if (session.status !== 'running') continue
      const existing = workingSessions.value.get(session.session_id)
      const updatedTime = Date.parse(session.updated_time || '')
      updated.set(session.session_id, {
        sessionName: session.name || existing?.sessionName || '',
        projectName: projectNames.get(session.project_id) || existing?.projectName || '',
        startTime: existing?.startTime || (Number.isFinite(updatedTime) ? updatedTime : Date.now()),
      })
    }

    workingSessions.value = updated
  }

  return {
    workingCount,
    workingList,
    markWorking,
    markDone,
    syncWorkingSessions,
  }
}
