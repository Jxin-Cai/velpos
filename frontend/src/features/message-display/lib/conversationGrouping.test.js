import test from 'node:test'
import assert from 'node:assert/strict'

import { finalAnswerIndex, groupConversationMessages } from './conversationGrouping.js'

test('test_starts_a_new_turn_when_a_user_message_arrives', () => {
  // Arrange
  const messages = [
    { type: 'user', content: { text: 'First' } },
    { type: 'result', content: { text: 'First answer' } },
    { type: 'user', content: { text: 'Second' } },
    { type: 'result', content: { text: 'Second answer' } },
  ]

  // Act
  const groups = groupConversationMessages(messages)

  // Assert
  assert.deepEqual(groups.map(group => group.messages.length), [2, 2])
})

test('test_keeps_leading_system_output_in_a_single_turn', () => {
  // Arrange
  const messages = [
    { type: 'system', content: { subtype: 'connected' } },
    { type: 'result', content: { text: 'Restored answer' } },
  ]

  // Act
  const groups = groupConversationMessages(messages)

  // Assert
  assert.equal(groups.length, 1)
})

test('test_marks_the_last_successful_result_as_the_final_answer', () => {
  // Arrange
  const messages = [
    { type: 'result', content: { text: 'Draft' } },
    { type: 'artifact', content: { path: '/tmp/report.md' } },
    { type: 'result', content: { text: 'Final' } },
  ]

  // Act
  const index = finalAnswerIndex(messages)

  // Assert
  assert.equal(index, 2)
})
