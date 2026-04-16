import { marked } from 'marked'
import DOMPurify from 'dompurify'

const renderer = new marked.Renderer()
const originalLinkRenderer = renderer.link.bind(renderer)
renderer.link = function (token) {
  const html = originalLinkRenderer(token)
  // Ensure all links open in new tab with security attributes
  return html.replace(/^<a /, '<a target="_blank" rel="noopener noreferrer" ')
}

function escapeHtml(str) {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

// Wrap code blocks with a copy button
const originalCodeRenderer = renderer.code.bind(renderer)
renderer.code = function (token) {
  const html = originalCodeRenderer(token)
  const lang = token.lang || ''
  const langLabel = lang ? `<span class="code-lang">${escapeHtml(lang)}</span>` : ''
  return `<div class="code-block-wrapper">${langLabel}<button class="code-copy-btn" title="Copy code"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg></button>${html}</div>`
}

// File path extension: detect absolute paths like /Users/xxx/file.ext in inline text
const filePathExtension = {
  name: 'filePath',
  level: 'inline',
  start(src) {
    // Look for absolute paths: /word or ~/word (but not inside markdown links/code)
    const m = src.match(/(?:^|[\s(])(?=\/[A-Za-z])/)
    return m ? m.index + (m[0].length - m[0].trimStart().length) : -1
  },
  tokenizer(src) {
    // Match absolute paths: /path/to/something or ~/path/to/something
    const match = src.match(/^(\/(?:[A-Za-z0-9._-]+\/)*[A-Za-z0-9._-]+)/)
    if (match) {
      return {
        type: 'filePath',
        raw: match[0],
        path: match[1],
      }
    }
  },
  renderer(token) {
    const escaped = escapeHtml(token.path)
    // File path links are internal, don't add external icon
    return `<a class="file-path-link" data-file-path="${escaped}" href="javascript:void(0)" title="Click to open">${escaped}</a>`
  },
}

// URL extension: auto-link URLs in text that aren't already in markdown links
const urlExtension = {
  name: 'url',
  level: 'inline',
  start(src) {
    // Look for http:// or https:// at start of line or after whitespace/punctuation
    const match = src.match(/(?:^|[\s(])(?=https?:\/\/)/)
    return match ? match.index + (match[0].length - match[0].trimStart().length) : -1
  },
  tokenizer(src) {
    // Match URLs but not if they're already part of markdown syntax
    // Don't match if preceded by ] (which would indicate a markdown link)
    if (src.match(/^\]/)) return null

    const match = src.match(/^(https?:\/\/[^\s<>"{}|\\^`\[\]]+)/)
    if (match) {
      return {
        type: 'url',
        raw: match[0],
        url: match[1],
      }
    }
  },
  renderer(token) {
    const escaped = escapeHtml(token.url)
    return `<a href="${escaped}" target="_blank" rel="noopener noreferrer" class="auto-link">${escaped}</a>`
  },
}

marked.use({ extensions: [filePathExtension, urlExtension] })

marked.setOptions({
  breaks: true,
  gfm: true,
  renderer,
})

// Configure DOMPurify to allow safe attributes for links
DOMPurify.addHook('uponSanitizeAttribute', function (node, data) {
  // Allow target="_blank" and rel="noopener noreferrer" for links
  if (data.attrName === 'target' && node.tagName === 'A') {
    node.setAttribute('target', '_blank')
  }
  if (data.attrName === 'rel' && node.tagName === 'A') {
    node.setAttribute('rel', 'noopener noreferrer')
  }
})

export function configuredMarked(text) {
  return DOMPurify.sanitize(marked.parse(text), {
    ALLOWED_ATTR: ['target', 'rel', 'href', 'class', 'data-file-path', 'title'],
    ALLOW_DATA_ATTR: true
  })
}
