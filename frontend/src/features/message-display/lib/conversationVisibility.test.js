import test from 'node:test'
import assert from 'node:assert/strict'

import { filterConversationMessages } from './conversationVisibility.js'

test('test_keeps_only_public_conversation_content_when_debug_is_disabled', () => {
  // Arrange
  const messages = [
    { type: 'user', content: { text: 'Build it' } },
    { type: 'assistant', content: { blocks: [{ type: 'text', text: 'Inspecting files' }] } },
    { type: 'tool_result', content: { results: [{ content: 'ok', is_error: false }] } },
    { type: 'interactive', content: { interaction_type: 'permission' } },
    { type: 'result', content: { text: 'Done', is_error: false } },
  ]

  // Act
  const filtered = filterConversationMessages(messages)

  // Assert
  assert.deepEqual(filtered.map(message => message.type), ['user', 'interactive', 'result'])
})

test('test_keeps_artifact_context_when_assistant_contains_internal_blocks', () => {
  // Arrange
  const messages = [{
    type: 'assistant',
    content: {
      blocks: [
        { type: 'thinking', thinking: 'internal' },
        { type: 'tool_use', name: 'Read' },
        { type: 'tool_result', content: 'failed', is_error: true },
        { type: 'text', text: 'The generated report is ready.' },
        { type: 'artifact', path: '/tmp/report.pdf' },
      ],
    },
  }]

  // Act
  const [filtered] = filterConversationMessages(messages)

  // Assert
  assert.deepEqual(
    filtered.content.blocks.map(block => block.type),
    ['text', 'artifact'],
  )
})

test('test_keeps_assistant_context_when_text_contains_a_file_path', () => {
  // Arrange
  const message = {
    type: 'assistant',
    content: { blocks: [{ type: 'text', text: 'Open the report at /tmp/output/report.pdf for details.' }] },
  }

  // Act
  const filtered = filterConversationMessages([message])

  // Assert
  assert.deepEqual(filtered, [message])
})

test('test_keeps_assistant_context_when_text_contains_a_web_link', () => {
  // Arrange
  const message = {
    type: 'assistant',
    content: { blocks: [{ type: 'text', text: 'Preview: https://example.com/report' }] },
  }

  // Act
  const filtered = filterConversationMessages([message])

  // Assert
  assert.deepEqual(filtered, [message])
})

test('test_replaces_file_tool_result_container_with_public_text_when_debug_is_disabled', () => {
  // Arrange
  const message = {
    type: 'tool_result',
    content: { results: [{ content: 'Saved to /tmp/output/report.pdf', is_error: false }] },
  }

  // Act
  const filtered = filterConversationMessages([message])

  // Assert
  assert.deepEqual(filtered, [{
    type: 'assistant',
    content: { blocks: [{ type: 'text', text: 'Saved to /tmp/output/report.pdf' }] },
  }])
})

test('test_removes_unrelated_results_from_file_tool_output_when_debug_is_disabled', () => {
  // Arrange
  const fileResult = { content: 'Saved to /tmp/output/report.pdf', is_error: false }
  const message = {
    type: 'tool_result',
    content: {
      results: [
        { content: 'Read 42 records', is_error: false },
        fileResult,
      ],
    },
  }

  // Act
  const [filtered] = filterConversationMessages([message])

  // Assert
  assert.deepEqual(filtered.content.blocks, [{
    type: 'text',
    text: fileResult.content,
  }])
})

test('test_shows_tool_calls_when_debug_is_enabled', () => {
  // Arrange
  const messages = [{
    type: 'assistant',
    content: { blocks: [{ type: 'tool_use', name: 'Read', input: { path: '/tmp/file.txt' } }] },
  }]

  // Act
  const filtered = filterConversationMessages(messages, { debug: true })

  // Assert
  assert.equal(filtered, messages)
})

test('test_shows_system_messages_when_debug_is_enabled', () => {
  // Arrange
  const messages = [
    { type: 'system', content: { subtype: 'thinking_tokens' } },
    { type: 'system', content: { subtype: 'task_progress' } },
  ]

  // Act
  const filtered = filterConversationMessages(messages, { debug: true })

  // Assert
  assert.equal(filtered, messages)
})

test('test_keeps_unrelated_results_in_same_batch_when_debug_is_enabled', () => {
  // Arrange
  const messages = [{
    type: 'tool_result',
    content: {
      results: [
        { content: 'Read 42 records', is_error: false },
        { content: 'Saved to /tmp/output/report.pdf', is_error: false },
      ],
    },
  }]

  // Act
  const filtered = filterConversationMessages(messages, { debug: true })

  // Assert
  assert.equal(filtered, messages)
})

test('test_hides_errors_when_debug_is_disabled', () => {
  // Arrange
  const messages = [
    { type: 'error', content: { message: 'connection failed' } },
    { type: 'result', content: { text: 'request failed', is_error: true } },
    {
      type: 'tool_result',
      content: { results: [{ content: 'denied', is_error: true }] },
    },
    { type: 'system', content: { error: 'stream failed' } },
  ]

  // Act
  const filtered = filterConversationMessages(messages)

  // Assert
  assert.deepEqual(filtered, [])
})
