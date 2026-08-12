import test from 'node:test'
import assert from 'node:assert/strict'

import {
  flattenTraceTree,
  mergeTraceSpans,
  resolveSelectedRunId,
} from './traceHistory.js'

test('test_keeps_explicit_run_when_recent_history_does_not_contain_it', () => {
  // Arrange
  const recentSpans = [{ id: 'new-run', run_id: 'run-2' }]

  // Act
  const selectedRunId = resolveSelectedRunId('run-1', recentSpans)

  // Assert
  assert.equal(selectedRunId, 'run-1')
})

test('test_selects_latest_run_when_no_run_was_explicitly_selected', () => {
  // Arrange
  const spans = [
    { id: 'old-run', run_id: 'run-1' },
    { id: 'new-run', run_id: 'run-2' },
  ]

  // Act
  const selectedRunId = resolveSelectedRunId(null, spans)

  // Assert
  assert.equal(selectedRunId, 'run-2')
})

test('test_merges_hydrated_older_run_with_recent_history', () => {
  // Arrange
  const recentSpans = [{ id: 'new-run', run_id: 'run-2', started_time: '2026-08-12T16:00:00' }]
  const olderTree = [{
    id: 'old-run',
    run_id: 'run-1',
    started_time: '2026-08-12T14:00:00',
    children: [{ id: 'old-step', run_id: 'run-1', started_time: '2026-08-12T14:00:01' }],
  }]

  // Act
  const merged = mergeTraceSpans(recentSpans, flattenTraceTree(olderTree))

  // Assert
  assert.deepEqual(merged.map(span => span.id), ['old-run', 'old-step', 'new-run'])
})
