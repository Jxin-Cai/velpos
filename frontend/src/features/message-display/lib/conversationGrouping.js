function messageKey(message, fallback) {
  return message?._id ?? message?.id ?? message?._index ?? fallback
}

export function groupConversationMessages(messages = []) {
  const groups = []
  let currentGroup = null

  for (const [index, message] of messages.entries()) {
    if (message?.type === 'user' || !currentGroup) {
      currentGroup = {
        key: `turn-${messageKey(message, index)}`,
        messages: [],
      }
      groups.push(currentGroup)
    }
    currentGroup.messages.push(message)
  }

  return groups
}

export function finalAnswerIndex(messages = []) {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index]
    if (message?.type === 'result' && !message.content?.is_error && message.content?.text) {
      return index
    }
  }
  return -1
}
