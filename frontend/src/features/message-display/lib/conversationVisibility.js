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

function blockText(block) {
  if (typeof block === 'string') return block
  if (typeof block?.text === 'string') return block.text
  if (typeof block?.content === 'string') return block.content
  return ''
}

function hasFileOrLinkReference(value) {
  const text = typeof value === 'string' ? value : JSON.stringify(value || '')
  return /https?:\/\/\S+/i.test(text)
    || /(?:^|[\s(`[])~?\/[A-Za-z0-9._-]+(?:\/[A-Za-z0-9._-]+)+/m.test(text)
    || /(?:^|[\s(`[])(?:\.\.?\/)?(?:[A-Za-z0-9._-]+\/)+[A-Za-z0-9._-]+\.[A-Za-z0-9]{1,10}/m.test(text)
    || /[A-Za-z]:\\(?:[^\\\s]+\\)+[^\\\s]+/.test(text)
}

function readableResultContent(value) {
  if (typeof value === 'string') return value
  if (Array.isArray(value)) {
    return value
      .map(item => blockText(item) || JSON.stringify(item, null, 2))
      .filter(Boolean)
      .join('\n\n')
  }
  return blockText(value) || JSON.stringify(value, null, 2)
}

function publicFileResultMessage(message, results) {
  const blocks = results
    .map(result => readableResultContent(result?.content))
    .filter(hasText)
    .map(text => ({ type: 'text', text }))

  return blocks.length
    ? { ...message, type: 'assistant', content: { blocks } }
    : null
}

function visibleAssistantBlocks(blocks = []) {
  const hasReference = blocks.some(block => (
    isArtifactBlock(block)
    || (block?.type === 'text' && hasFileOrLinkReference(blockText(block)))
  ))
  if (!hasReference) return []
  return blocks.filter(block => block?.type === 'text' || isArtifactBlock(block))
}

/**
 * Keep the main conversation focused on the same public surface as Codex:
 * user input, successful final responses, interaction requests, and artifacts.
 * Normal mode hides raw model turns and tool execution details. Debug mode
 * intentionally returns the complete event stream for troubleshooting.
 */
export function filterConversationMessages(messages = [], { debug = false } = {}) {
  const isIgnoredSystemMessage = message => (
    message?.type === 'system'
    && IGNORED_SYSTEM_SUBTYPES.has(message?.content?.subtype)
  )

  if (debug) return messages

  return messages.flatMap(message => {
    if (isIgnoredSystemMessage(message)) return []
    const content = message?.content || {}

    if (message?.type === 'user' || message?.type === 'interactive' || message?.type === 'artifact') {
      return [message]
    }

    if (message?.type === 'result') {
      return !content.is_error && hasText(content.text) ? [message] : []
    }

    if (message?.type === 'tool_result') {
      const results = (content.results || []).filter(result => hasFileOrLinkReference(result?.content))
      const publicMessage = publicFileResultMessage(message, results)
      return publicMessage ? [publicMessage] : []
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
