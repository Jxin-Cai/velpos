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

export function markInteractiveMessageAnswered(messages, targetMessage) {
  const signature = interactionSignature(targetMessage)
  if (!signature) return false

  const message = messages.find(candidate => interactionSignature(candidate) === signature)
  if (!message) return false

  message.content = {
    ...message.content,
    interaction_answered: true,
  }
  return true
}

export function preserveInteractiveAnswerState(currentMessages, incomingMessages) {
  const answeredSignatures = new Set(
    currentMessages
      .filter(message => message.content?.interaction_answered)
      .map(interactionSignature)
      .filter(Boolean),
  )

  return incomingMessages.map(message => {
    if (!answeredSignatures.has(interactionSignature(message))) return message
    return {
      ...message,
      content: {
        ...message.content,
        interaction_answered: true,
      },
    }
  })
}
