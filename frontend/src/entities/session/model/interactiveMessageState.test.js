import assert from 'node:assert/strict'
import test from 'node:test'

import {
  markInteractiveMessageAnswered,
  preserveInteractiveAnswerState,
} from './interactiveMessageState.js'

function choiceMessage(index = 3) {
  return {
    _index: index,
    type: 'interactive',
    content: {
      interaction_type: 'user_choice',
      tool_name: 'AskUserQuestion',
      questions: [{ question: 'Choose', options: [{ label: 'A' }] }],
    },
  }
}

test('test_marks_matching_interaction_answered_when_response_is_sent', () => {
  // Arrange
  const message = choiceMessage()
  const messages = [message]

  // Act
  const marked = markInteractiveMessageAnswered(messages, message)

  // Assert
  assert.equal(marked, true)
  assert.equal(messages[0].content.interaction_answered, true)
})

test('test_preserves_answered_state_when_message_snapshot_is_replaced', () => {
  // Arrange
  const current = choiceMessage()
  current.content.interaction_answered = true
  const incoming = choiceMessage()

  // Act
  const merged = preserveInteractiveAnswerState([current], [incoming])

  // Assert
  assert.equal(merged[0].content.interaction_answered, true)
})

test('test_does_not_mark_different_interaction_when_index_is_reused', () => {
  // Arrange
  const current = choiceMessage()
  current.content.interaction_answered = true
  const incoming = choiceMessage()
  incoming.content.questions[0].question = 'Choose again'

  // Act
  const merged = preserveInteractiveAnswerState([current], [incoming])

  // Assert
  assert.equal(merged[0].content.interaction_answered, undefined)
})
