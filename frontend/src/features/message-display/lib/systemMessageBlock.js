export function buildSystemMessageBlock(content = {}) {
  const subtype = content.subtype || ''

  if (subtype === 'auto_continue') {
    return {
      type: 'system',
      text: `Auto-continuing (${content.attempt}/${content.max})`,
      markdown: '',
    }
  }

  let text = subtype
  if (content.description) text += `: ${content.description}`
  if (content.status) text += ` [${content.status}]`
  if (content.last_tool_name) text += ` (${content.last_tool_name})`

  return {
    type: 'system',
    text: text || JSON.stringify(content),
    markdown: typeof content.summary === 'string' ? content.summary : '',
  }
}
