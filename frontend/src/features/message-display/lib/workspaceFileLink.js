const LOCAL_FILE_HOSTS = new Set(['localhost', '127.0.0.1', '::1'])
const UNIX_FILE_ROOT = /^\/(?:Users|home|root|workspace|tmp|private|opt|mnt|Volumes|srv|app)\//
const WINDOWS_FILE_ROOT = /^\/[A-Za-z]:\//

function decodedPathname(value) {
  try {
    return decodeURIComponent(value)
  } catch (error) {
    if (error instanceof URIError) return value
    throw error
  }
}

function isWorkspaceFilePath(path) {
  return UNIX_FILE_ROOT.test(path) || WINDOWS_FILE_ROOT.test(path)
}

export function extractWorkspaceFilePath(href) {
  const value = String(href || '').trim()
  if (!value) return ''

  if (value.startsWith('file://')) {
    try {
      const url = new URL(value)
      const path = decodedPathname(url.pathname)
      const isLocal = !url.hostname || LOCAL_FILE_HOSTS.has(url.hostname)
      return isLocal && isWorkspaceFilePath(path) ? path : ''
    } catch (error) {
      if (error instanceof TypeError) return ''
      throw error
    }
  }

  if (value.startsWith('/')) {
    const path = decodedPathname(value.split(/[?#]/, 1)[0])
    return isWorkspaceFilePath(path) ? path : ''
  }

  try {
    const url = new URL(value)
    const path = decodedPathname(url.pathname)
    return LOCAL_FILE_HOSTS.has(url.hostname) && isWorkspaceFilePath(path) ? path : ''
  } catch (error) {
    if (error instanceof TypeError) return ''
    throw error
  }
}
