import { ref } from 'vue'
import { useSession, clearContext as clearContextApi } from '@entities/session'

export function useClearContext() {
  const { setMessages, setStatus } = useSession()
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
    } finally {
      clearing.value = false
    }
  }

  return { clearing, clearContext }
}
