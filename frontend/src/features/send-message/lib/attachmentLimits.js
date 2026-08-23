import { formatFileSize } from '../../../shared/lib/textParsers.js'

// Keep decoded attachments under the WebSocket 16MB frame limit after base64 (~4/3).
export const MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
export const MAX_ATTACHMENT_LABEL = '10 MB'

export function decodedSizeFromBase64(base64) {
  if (!base64) return 0
  const padding = base64.endsWith('==') ? 2 : base64.endsWith('=') ? 1 : 0
  return Math.max(0, Math.floor((base64.length * 3) / 4) - padding)
}

export function attachmentByteSize(item) {
  const declared = Number(item?.size || item?.size_bytes || 0)
  if (declared > 0) return declared
  return decodedSizeFromBase64(item?.data || '')
}

export function describeOversizeFile(name, size) {
  const filename = name || 'attachment'
  return `${filename} is ${formatFileSize(size)}, which exceeds the ${MAX_ATTACHMENT_LABEL} attachment limit.`
}

export function describeOversizeTotal(total) {
  return `Attachments total ${formatFileSize(total)}, which exceeds the ${MAX_ATTACHMENT_LABEL} limit.`
}

export function validateIncomingFile(file, existingAttachments = []) {
  const name = file?.name || 'attachment'
  const size = Number(file?.size || 0)
  if (size > MAX_ATTACHMENT_BYTES) {
    return describeOversizeFile(name, size)
  }
  const existingTotal = existingAttachments.reduce(
    (sum, item) => sum + attachmentByteSize(item),
    0,
  )
  if (existingTotal + size > MAX_ATTACHMENT_BYTES) {
    return describeOversizeTotal(existingTotal + size)
  }
  return ''
}

export function validateOutgoingAttachments(attachments = []) {
  let total = 0
  for (const item of attachments) {
    const size = attachmentByteSize(item)
    const name = item?.name || item?.filename || 'attachment'
    if (size > MAX_ATTACHMENT_BYTES) {
      return `${describeOversizeFile(name, size)} The message was not sent.`
    }
    total += size
  }
  if (total > MAX_ATTACHMENT_BYTES) {
    return `${describeOversizeTotal(total)} The message was not sent.`
  }
  return ''
}
