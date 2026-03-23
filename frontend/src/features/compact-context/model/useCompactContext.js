import { ref } from 'vue'
import { compactSession } from '@entities/session'

export function useCompactContext() {
  const compacting = ref(false)

  async function compactContext(sessionId) {
    if (!sessionId) return
    compacting.value = true
    try {
      await compactSession(sessionId)
    } catch (err) {
      console.error('Failed to compact context:', err)
    } finally {
      compacting.value = false
    }
  }

  return { compacting, compactContext }
}
