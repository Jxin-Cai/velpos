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

test('test_keeps_error_and_artifact_blocks_when_assistant_contains_internal_blocks', () => {
  // Arrange
  const messages = [{
    type: 'assistant',
    content: {
      blocks: [
        { type: 'thinking', thinking: 'internal' },
        { type: 'tool_use', name: 'Read' },
        { type: 'tool_result', content: 'failed', is_error: true },
        { type: 'artifact', path: '/tmp/report.pdf' },
      ],
    },
  }]

  // Act
  const [filtered] = filterConversationMessages(messages)

  // Assert
  assert.deepEqual(
    filtered.content.blocks.map(block => block.type),
    ['tool_result', 'artifact'],
  )
})

test('test_returns_original_messages_when_debug_is_enabled', () => {
  // Arrange
  const messages = [{ type: 'system', content: { subtype: 'task_progress' } }]

  // Act
  const filtered = filterConversationMessages(messages, { debug: true })

  // Assert
  assert.equal(filtered, messages)
})

test('test_keeps_only_failed_results_when_tool_results_are_mixed', () => {
  // Arrange
  const messages = [{
    type: 'tool_result',
    content: {
      results: [
        { tool_use_id: 'success', content: 'ok', is_error: false },
        { tool_use_id: 'failure', content: 'denied', is_error: true },
      ],
    },
  }]

  // Act
  const [filtered] = filterConversationMessages(messages)

  // Assert
  assert.equal(filtered.content.results[0].tool_use_id, 'failure')
})
