const ARTIFACT_BLOCK_TYPES = new Set([
  'artifact',
  'attachment',
  'file',
  'image',
  'output_file',
])

function hasText(value) {
  return typeof value === 'string' && value.trim().length > 0
}

function isErrorBlock(block) {
  return Boolean(block?.is_error || block?.error)
}

function isArtifactBlock(block) {
  return ARTIFACT_BLOCK_TYPES.has(block?.type)
}

function visibleAssistantBlocks(blocks = []) {
  return blocks.filter(block => isErrorBlock(block) || isArtifactBlock(block))
}

function visibleToolResults(results = []) {
  return results.filter(result => isErrorBlock(result) || isArtifactBlock(result))
}

/**
 * Keep the main conversation focused on the same public surface as Codex:
 * user input, final responses, interaction requests, errors, and artifacts.
 * Raw model turns and execution details remain available in debug mode.
 */
export function filterConversationMessages(messages = [], { debug = false } = {}) {
  if (debug) return messages

  return messages.flatMap(message => {
    const content = message?.content || {}

    if (message?.type === 'user' || message?.type === 'interactive' || message?.type === 'artifact') {
      return [message]
    }

    if (message?.type === 'result') {
      return content.is_error || hasText(content.text) ? [message] : []
    }

    if (message?.type === 'error') {
      return [message]
    }

    if (message?.type === 'assistant') {
      const blocks = visibleAssistantBlocks(content.blocks)
      return blocks.length
        ? [{ ...message, content: { ...content, blocks } }]
        : []
    }

    if (message?.type === 'tool_result') {
      const results = visibleToolResults(content.results)
      return results.length
        ? [{ ...message, content: { ...content, results } }]
        : []
    }

    if (message?.type === 'system' && (content.is_error || content.error)) {
      return [message]
    }

    return []
  })
}

