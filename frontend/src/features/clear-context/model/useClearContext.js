import { ref } from 'vue'
import { useSession, clearContext as clearContextApi } from '@entities/session'

export function useClearContext() {
  const { setMessages, setStatus, setError } = useSession()
  const clearing = ref(false)

  async function clearContext(sessionId) {
    if (!sessionId) return
    clearing.value = true
    try {
      await clearContextApi(sessionId)
      setMessages([])
      setStatus('idle')
    } catch (err) {
      console.error('Failed to clear context:', err)
      setError('Failed to clear context: ' + (err.message || 'Unknown error'))
    } finally {
      clearing.value = false
    }
  }

  return { clearing, clearContext }
}
