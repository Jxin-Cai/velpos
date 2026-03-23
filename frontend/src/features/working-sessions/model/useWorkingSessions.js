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

  function isWorking(sessionId) {
    return workingSessions.value.has(sessionId)
  }

  return {
    workingSessions,
    workingCount,
    workingList,
    markWorking,
    markDone,
    isWorking,
  }
}
