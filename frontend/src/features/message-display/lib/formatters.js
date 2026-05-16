export function formatDuration(ms, fallback = '') {
  if (!ms) return fallback
  const s = (ms / 1000).toFixed(1)
  return `${s}s`
}

export function formatDurationLong(ms, fallback = '') {
  if (!ms) return fallback
  const secs = Math.floor(Math.max(0, ms) / 1000)
  if (secs < 60) return `${secs}s`
  const mins = Math.floor(secs / 60)
  const remainSecs = secs % 60
  if (mins < 60) return `${mins}m ${remainSecs}s`
  const hrs = Math.floor(mins / 60)
  return `${hrs}h ${mins % 60}m`
}

export function formatInput(input) {
  if (!input || typeof input !== 'object') return ''
  try {
    return JSON.stringify(input, null, 2)
  } catch {
    return String(input)
  }
}
