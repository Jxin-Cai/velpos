const IMAGE_EXTENSIONS = new Set([
  'png', 'jpg', 'jpeg', 'gif', 'svg', 'webp', 'bmp', 'ico', 'avif',
])

const PDF_EXTENSIONS = new Set(['pdf'])

const EXCEL_EXTENSIONS = new Set(['xlsx', 'xls', 'csv'])

const VIDEO_EXTENSIONS = new Set([
  'mp4', 'webm', 'mov', 'm4v', 'ogv', 'avi', 'mkv',
])

const AUDIO_EXTENSIONS = new Set([
  'mp3', 'wav', 'ogg', 'oga', 'm4a', 'aac', 'flac', 'opus',
])

export function getFilePreviewType(path) {
  const ext = (path || '').split('.').pop()?.toLowerCase() || ''
  if (IMAGE_EXTENSIONS.has(ext)) return 'image'
  if (PDF_EXTENSIONS.has(ext)) return 'pdf'
  if (EXCEL_EXTENSIONS.has(ext)) return 'excel'
  if (VIDEO_EXTENSIONS.has(ext)) return 'video'
  if (AUDIO_EXTENSIONS.has(ext)) return 'audio'
  return null
}

export function getFileRawUrl(projectId, filePath) {
  return `/api/projects/${projectId}/workspace/file-raw?path=${encodeURIComponent(filePath)}`
}

export function getHtmlPreviewUrl(projectId, filePath) {
  const encodedProjectId = encodeURIComponent(projectId)
  const encodedPath = String(filePath || '')
    .replace(/\\/g, '/')
    .split('/')
    .map(segment => encodeURIComponent(segment))
    .join('/')
  return `/api/projects/${encodedProjectId}/workspace/file-preview/${encodedPath}`
}
