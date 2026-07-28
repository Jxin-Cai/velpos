const ATTACHMENT_REFERENCE_PATTERN = /\n{0,2}\[(?:Image|Attachment):\s*[^\]]+\]/g

export function visibleUserText(content = {}) {
  if (typeof content.raw_prompt === 'string') return content.raw_prompt

  const text = String(content.text || '')
  if (!content.attachments?.length) return text

  return text.replace(ATTACHMENT_REFERENCE_PATTERN, '').trim()
}
