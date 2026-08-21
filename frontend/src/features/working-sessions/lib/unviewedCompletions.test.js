import test from 'node:test'
import assert from 'node:assert/strict'

import { applyCompletionViewState, markSessionViewed, pruneUnviewedIds } from './unviewedCompletions.js'

test('test_marks_background_completion_as_unviewed', () => {
  const next = applyCompletionViewState(new Set(), 's1', { wasWorking: true, isCurrent: false })

  assert.deepEqual([...next], ['s1'])
})

test('test_does_not_mark_current_session_as_unviewed', () => {
  const next = applyCompletionViewState(new Set(['s1']), 's1', { wasWorking: true, isCurrent: true })

  assert.deepEqual([...next], [])
})

test('test_ignores_idle_session_that_was_not_working', () => {
  const next = applyCompletionViewState(new Set(), 's1', { wasWorking: false, isCurrent: false })

  assert.deepEqual([...next], [])
})

test('test_clears_unviewed_when_session_is_opened', () => {
  const next = markSessionViewed(new Set(['s1', 's2']), 's1')

  assert.deepEqual([...next], ['s2'])
})

test('test_drops_unviewed_ids_that_no_longer_exist', () => {
  const next = pruneUnviewedIds(new Set(['s1', 'gone']), new Set(['s1']))

  assert.deepEqual([...next], ['s1'])
})
