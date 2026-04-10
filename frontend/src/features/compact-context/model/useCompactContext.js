import { ref } from 'vue'
import { useSession } from '@entities/session'
import { compactSession } from '@entities/session'

export function useCompactContext() {
  const { setError } = useSession()
  const compacting = ref(false)

  async function compactContext(sessionId) {
    if (!sessionId) return
    compacting.value = true
    try {
      await compactSession(sessionId)
    } catch (err) {
      console.error('Failed to compact context:', err)
      setError('Failed to compact context: ' + (err.message || 'Unknown error'))
    } finally {
      compacting.value = false
    }
  }

  return { compacting, compactContext }
}
