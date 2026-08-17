export function formatTokens(value, { precision = 1 } = {}) {
  const number = Math.max(Number(value) || 0, 0)
  if (number >= 1_000_000) return `${(number / 1_000_000).toFixed(precision)}m`
  if (number >= 1_000) return `${(number / 1_000).toFixed(precision)}k`
  return String(number)
}
