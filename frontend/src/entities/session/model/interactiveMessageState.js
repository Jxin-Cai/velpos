function interactionSignature(message) {
  const content = message?.content
  if (message?.type !== 'interactive' || !content?.interaction_type) return ''

  return JSON.stringify({
    index: message._index,
    interactionType: content.interaction_type,
    toolName: content.tool_name || '',
    questions: content.questions || [],
    toolInput: content.tool_input || '',
  })
}

function storageKey(sessionId, message) {
  const signature = interactionSignature(message)
  return sessionId && signature
    ? `velpos:interactive-answer:${sessionId}:${signature}`
    : ''
}

export function restoreInteractiveAnswerState(sessionId, message, storage = globalThis.sessionStorage) {
  const key = storageKey(sessionId, message)
  if (!key || !storage) return message

  const saved = storage.getItem(key)
  if (!saved) return message

  const response = JSON.parse(saved)
  return {
    ...message,
    content: {
      ...message.content,
      interaction_answered: true,
      interaction_response: response,
    },
  }
}

export function markInteractiveMessageAnswered(
  messages,
  targetMessage,
  response = {},
  sessionId = '',
  storage = globalThis.sessionStorage,
) {
  const signature = interactionSignature(targetMessage)
  if (!signature) return false

  const message = messages.find(candidate => interactionSignature(candidate) === signature)
  if (!message) return false

  message.content = {
    ...message.content,
    interaction_answered: true,
    interaction_response: response,
  }
  const key = storageKey(sessionId, message)
  if (key && storage) storage.setItem(key, JSON.stringify(response))
  return true
}

export function preserveInteractiveAnswerState(currentMessages, incomingMessages) {
  const answeredState = new Map(
    currentMessages
      .filter(message => message.content?.interaction_answered)
      .map(message => [interactionSignature(message), message.content.interaction_response || {}])
      .filter(([signature]) => Boolean(signature)),
  )

  return incomingMessages.map(message => {
    const response = answeredState.get(interactionSignature(message))
    if (!response) return message
    return {
      ...message,
      content: {
        ...message.content,
        interaction_answered: true,
        interaction_response: response,
      },
    }
  })
}
