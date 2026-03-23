import { marked } from 'marked'
import DOMPurify from 'dompurify'

const renderer = new marked.Renderer()
const originalLinkRenderer = renderer.link.bind(renderer)
renderer.link = function (token) {
  const html = originalLinkRenderer(token)
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
    return `<a class="file-path-link" data-file-path="${escaped}" href="javascript:void(0)" title="Click to open">${escaped}</a>`
  },
}

marked.use({ extensions: [filePathExtension] })

marked.setOptions({
  breaks: true,
  gfm: true,
  renderer,
})

export function configuredMarked(text) {
  return DOMPurify.sanitize(marked.parse(text))
}
