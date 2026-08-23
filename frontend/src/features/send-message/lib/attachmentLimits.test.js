import assert from 'node:assert/strict'
import test from 'node:test'

import {
  MAX_ATTACHMENT_BYTES,
  attachmentByteSize,
  decodedSizeFromBase64,
  validateIncomingFile,
  validateOutgoingAttachments,
} from './attachmentLimits.js'

test('test_rejects_incoming_file_when_it_exceeds_attachment_limit', () => {
  // Arrange
  const file = { name: 'report.pdf', size: MAX_ATTACHMENT_BYTES + 1 }

  // Act
  const error = validateIncomingFile(file)

  // Assert
  assert.match(error, /report\.pdf/)
  assert.match(error, /10 MB/)
  assert.doesNotMatch(error, /was not sent/)
})

test('test_rejects_incoming_file_when_existing_attachments_would_exceed_limit', () => {
  // Arrange
  const existing = [{ name: 'a.pdf', size: 6 * 1024 * 1024 }]
  const file = { name: 'b.pdf', size: 5 * 1024 * 1024 }

  // Act
  const error = validateIncomingFile(file, existing)

  // Assert
  assert.match(error, /exceeds the 10 MB limit/)
})

test('test_allows_incoming_file_when_it_fits_remaining_attachment_budget', () => {
  // Arrange
  const existing = [{ name: 'notes.txt', size: 1024 }]
  const file = { name: 'photo.png', size: 2048 }

  // Act
  const error = validateIncomingFile(file, existing)

  // Assert
  assert.equal(error, '')
})

test('test_blocks_outgoing_message_when_attachment_exceeds_limit', () => {
  // Arrange
  const attachments = [{ name: 'deck.pdf', size: MAX_ATTACHMENT_BYTES + 1 }]

  // Act
  const error = validateOutgoingAttachments(attachments)

  // Assert
  assert.match(error, /deck\.pdf/)
  assert.match(error, /The message was not sent/)
})

test('test_blocks_outgoing_message_when_combined_attachments_exceed_limit', () => {
  // Arrange
  const attachments = [
    { name: 'a.bin', size: 6 * 1024 * 1024 },
    { name: 'b.bin', size: 5 * 1024 * 1024 },
  ]

  // Act
  const error = validateOutgoingAttachments(attachments)

  // Assert
  assert.match(error, /The message was not sent/)
})

test('test_uses_base64_payload_size_when_declared_size_is_missing', () => {
  // Arrange
  const data = Buffer.from('hello world').toString('base64')

  // Act
  const size = attachmentByteSize({ data })

  // Assert
  assert.equal(size, decodedSizeFromBase64(data))
  assert.equal(size, 11)
})
