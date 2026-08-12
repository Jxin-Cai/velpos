import assert from 'node:assert/strict'
import test from 'node:test'

import { extractWorkspaceFilePath } from './workspaceFileLink.js'

test('test_extracts_absolute_file_path_when_localhost_url_wraps_project_file', () => {
  // Arrange
  const href = 'http://localhost:3000/Users/jxin/velpos/.chisel/api-change-plan.json'

  // Act
  const path = extractWorkspaceFilePath(href)

  // Assert
  assert.equal(path, '/Users/jxin/velpos/.chisel/api-change-plan.json')
})

test('test_decodes_file_path_when_localhost_url_contains_escaped_characters', () => {
  // Arrange
  const href = 'http://127.0.0.1:3231/Users/jxin/My%20Project/change-plan.json'

  // Act
  const path = extractWorkspaceFilePath(href)

  // Assert
  assert.equal(path, '/Users/jxin/My Project/change-plan.json')
})

test('test_keeps_web_link_external_when_localhost_url_is_application_route', () => {
  // Arrange
  const href = 'http://localhost:3000/docs/getting-started'

  // Act
  const path = extractWorkspaceFilePath(href)

  // Assert
  assert.equal(path, '')
})

test('test_keeps_remote_url_external_when_path_looks_like_local_file', () => {
  // Arrange
  const href = 'https://example.com/Users/jxin/change-plan.json'

  // Act
  const path = extractWorkspaceFilePath(href)

  // Assert
  assert.equal(path, '')
})
