import { useSession } from '@entities/session'

export function useSendMessage(wsConnection) {
  const { setError, addMessage } = useSession()

  function sendPrompt(promptOrData) {
    if (!wsConnection || wsConnection.getReadyState() !== WebSocket.OPEN) {
      setError('Not connected')
      return
    }

    // Support both string and { text, images } format
    let text = ''
    let images = null

    if (typeof promptOrData === 'string') {
      text = promptOrData.trim()
    } else if (promptOrData && typeof promptOrData === 'object') {
      text = (promptOrData.text || '').trim()
      images = promptOrData.images || null
    }

    if (!text && (!images || images.length === 0)) {
      return
    }

    setError(null)

    const payload = { action: 'send_prompt', prompt: text }
    if (images && images.length > 0) {
      payload.images = images
    }
    const sent = wsConnection.send(payload)
    if (!sent) {
      setError('Connection lost, message not sent')
      return
    }

    addMessage({
      type: 'user',
      content: {
        text,
        ...(images && images.length > 0 ? { image_count: images.length } : {}),
      },
    })
  }

  return { sendPrompt }
}
