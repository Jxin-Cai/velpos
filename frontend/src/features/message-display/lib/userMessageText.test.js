import test from 'node:test'
import assert from 'node:assert/strict'

import { visibleUserText } from './userMessageText.js'

test('test_uses_raw_prompt_when_persisted_text_contains_attachment_path', () => {
  // Arrange
  const content = {
    text: '看一下\n\n[Image: .upload-file/example.png]',
    raw_prompt: '看一下',
    attachments: [{ filename: 'example.png' }],
  }

  // Act
  const visibleText = visibleUserText(content)

  // Assert
  assert.equal(visibleText, '看一下')
})

test('test_hides_legacy_attachment_reference_when_raw_prompt_is_missing', () => {
  // Arrange
  const content = {
    text: '[Attachment: report.pdf path=.upload-file/report.pdf]',
    attachments: [{ filename: 'report.pdf' }],
  }

  // Act
  const visibleText = visibleUserText(content)

  // Assert
  assert.equal(visibleText, '')
})

test('test_preserves_plain_text_when_message_has_no_attachments', () => {
  // Arrange
  const content = { text: 'Literal [Image: example] text' }

  // Act
  const visibleText = visibleUserText(content)

  // Assert
  assert.equal(visibleText, 'Literal [Image: example] text')
})
