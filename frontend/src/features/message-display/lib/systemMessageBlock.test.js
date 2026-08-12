import test from 'node:test'
import assert from 'node:assert/strict'

import { buildSystemMessageBlock } from './systemMessageBlock.js'

test('test_keeps_markdown_summary_separate_when_task_notification_completes', () => {
  // Arrange
  const summary = '# Implementation plan\n\n| Item | Choice |\n| --- | --- |\n| DB | SQLite |'

  // Act
  const block = buildSystemMessageBlock({
    subtype: 'task_notification',
    status: 'completed',
    summary,
  })

  // Assert
  assert.deepEqual(block, {
    type: 'system',
    text: 'task_notification [completed]',
    markdown: summary,
  })
})

test('test_formats_auto_continue_without_markdown_when_attempt_is_reported', () => {
  // Arrange
  const content = { subtype: 'auto_continue', attempt: 2, max: 3 }

  // Act
  const block = buildSystemMessageBlock(content)

  // Assert
  assert.deepEqual(block, {
    type: 'system',
    text: 'Auto-continuing (2/3)',
    markdown: '',
  })
})
