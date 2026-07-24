const ARTIFACT_BLOCK_TYPES = new Set([
  'artifact',
  'attachment',
  'file',
  'image',
  'output_file',
])

const IGNORED_SYSTEM_SUBTYPES = new Set([
  'thinking_tokens',
])

function hasText(value) {
  return typeof value === 'string' && value.trim().length > 0
}

function isArtifactBlock(block) {
  return ARTIFACT_BLOCK_TYPES.has(block?.type)
}

function visibleAssistantBlocks(blocks = []) {
  return blocks.filter(isArtifactBlock)
}

/**
 * Keep the main conversation focused on the same public surface as Codex:
 * user input, successful final responses, interaction requests, and artifacts.
 * Raw model turns and execution details remain available in debug mode.
 */
export function filterConversationMessages(messages = [], { debug = false } = {}) {
  const isIgnoredSystemMessage = message => (
    message?.type === 'system'
    && IGNORED_SYSTEM_SUBTYPES.has(message?.content?.subtype)
  )

  if (debug) {
    return messages.some(isIgnoredSystemMessage)
      ? messages.filter(message => !isIgnoredSystemMessage(message))
      : messages
  }

  return messages.flatMap(message => {
    if (isIgnoredSystemMessage(message)) return []
    const content = message?.content || {}

    if (message?.type === 'user' || message?.type === 'interactive' || message?.type === 'artifact') {
      return [message]
    }

    if (message?.type === 'result') {
      return !content.is_error && hasText(content.text) ? [message] : []
    }

    if (message?.type === 'assistant') {
      const blocks = visibleAssistantBlocks(content.blocks)
      return blocks.length
        ? [{ ...message, content: { ...content, blocks } }]
        : []
    }

    return []
  })
}
