import { useSession } from '@entities/session'

export function useSendMessage(wsConnection) {
  const { setError, addMessage } = useSession()

  function sendPrompt(promptOrData) {
    if (!wsConnection || wsConnection.getReadyState() !== WebSocket.OPEN) {
      setError('Not connected')
      return
    }

    // Support string and { text, images, attachments } formats
    let text = ''
    let images = null
    let attachments = null

    if (typeof promptOrData === 'string') {
      text = promptOrData.trim()
    } else if (promptOrData && typeof promptOrData === 'object') {
      text = (promptOrData.text || '').trim()
      images = promptOrData.images || null
      attachments = promptOrData.attachments || null
    }

    if (!text && (!images || images.length === 0) && (!attachments || attachments.length === 0)) {
      return
    }

    setError(null)

    const payload = { action: 'send_prompt', prompt: text }
    if (images && images.length > 0) {
      payload.images = images
    }
    if (attachments && attachments.length > 0) {
      payload.attachments = attachments
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
        ...(attachments && attachments.length > 0 ? { attachments: attachments.map(item => ({
          filename: item.name,
          mime_type: item.mime_type,
          size_bytes: item.size || 0,
        })) } : {}),
      },
    })
  }

  return { sendPrompt }
}
