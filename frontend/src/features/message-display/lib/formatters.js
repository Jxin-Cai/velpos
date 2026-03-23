export function formatDuration(ms) {
  if (!ms) return ''
  const s = (ms / 1000).toFixed(1)
  return `${s}s`
}

export function formatCost(usd) {
  if (!usd) return ''
  return `$${usd.toFixed(4)}`
}

export function formatInput(input) {
  if (!input || typeof input !== 'object') return ''
  try {
    return JSON.stringify(input, null, 2)
  } catch {
    return String(input)
  }
}
