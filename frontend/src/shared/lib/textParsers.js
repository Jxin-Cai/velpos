export function parseRulePaths(text = '') {
  return text
    .split('\n')
    .map(item => item.trim())
    .filter(Boolean)
}

export function formatFileSize(size) {
  const n = Number(size) || 0
  if (n >= 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`
  if (n >= 1024) return `${Math.round(n / 1024)} KB`
  return `${n} B`
}
