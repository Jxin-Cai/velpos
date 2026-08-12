import test from 'node:test'
import assert from 'node:assert/strict'

import { getHtmlPreviewUrl } from './fileTypes.js'

test('test_preserves_workspace_directories_when_html_preview_url_is_built', () => {
  // Arrange
  const projectId = 'project 1'
  const filePath = 'docs/examples/getting started.html'

  // Act
  const url = getHtmlPreviewUrl(projectId, filePath)

  // Assert
  assert.equal(
    url,
    '/api/projects/project%201/workspace/file-preview/docs/examples/getting%20started.html',
  )
})

test('test_normalizes_windows_separators_when_html_preview_url_is_built', () => {
  // Arrange
  const filePath = 'docs\\examples\\index.html'

  // Act
  const url = getHtmlPreviewUrl('project-1', filePath)

  // Assert
  assert.equal(
    url,
    '/api/projects/project-1/workspace/file-preview/docs/examples/index.html',
  )
})
