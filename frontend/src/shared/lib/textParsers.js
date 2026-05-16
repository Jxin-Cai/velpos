export function parseRulePaths(text = '') {
  return text
    .split('\n')
    .map(item => item.trim())
    .filter(Boolean)
}
