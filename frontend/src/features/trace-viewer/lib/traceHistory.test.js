import test from 'node:test'
import assert from 'node:assert/strict'

import {
  flattenTraceTree,
  listRunIds,
  mergeTraceSpans,
  resolveSelectedRunId,
  traceRunVersion,
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
    { id: 'old-run', run_id: 'run-1', started_time: '2026-08-12T14:00:00' },
    { id: 'new-run', run_id: 'run-2', started_time: '2026-08-12T16:00:00' },
  ]

  // Act
  const selectedRunId = resolveSelectedRunId(null, spans)

  // Assert
  assert.equal(selectedRunId, 'run-2')
})

test('test_lists_run_ids_in_chronological_call_order', () => {
  // Arrange — spans arrive with the selected older run appended last,
  // the same shape loadTraceForRun writes into session state.
  const spans = [
    { id: 'new-run', run_id: 'run-2', started_time: '2026-08-12T16:00:00' },
    { id: 'mid-run', run_id: 'run-3', started_time: '2026-08-12T15:00:00' },
    { id: 'old-run', run_id: 'run-1', started_time: '2026-08-12T14:00:00' },
  ]

  // Act
  const runIds = listRunIds(spans)

  // Assert
  assert.deepEqual(runIds, ['run-1', 'run-3', 'run-2'])
})

test('test_keeps_run_order_when_selected_run_spans_are_appended_last', () => {
  // Arrange
  const otherRuns = [
    { id: 'run-2-root', run_id: 'run-2', started_time: '2026-08-12T16:00:00' },
    { id: 'run-3-root', run_id: 'run-3', started_time: '2026-08-12T15:00:00' },
  ]
  const hydratedOlderRun = [
    { id: 'run-1-root', run_id: 'run-1', started_time: '2026-08-12T14:00:00' },
    { id: 'run-1-step', run_id: 'run-1', started_time: '2026-08-12T14:00:01' },
  ]

  // Act
  const runIds = listRunIds([...otherRuns, ...hydratedOlderRun])

  // Assert
  assert.deepEqual(runIds, ['run-1', 'run-3', 'run-2'])
  assert.equal(runIds.indexOf('run-1') + 1, 1)
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

test('test_changes_run_version_when_existing_span_revision_changes', () => {
  // Arrange
  const before = [{ id: 'tool-1', run_id: 'run-1', sequence: 4, revision: 1 }]
  const after = [{ id: 'tool-1', run_id: 'run-1', sequence: 5, revision: 2 }]

  // Act
  const beforeVersion = traceRunVersion(before, 'run-1')
  const afterVersion = traceRunVersion(after, 'run-1')

  // Assert
  assert.notEqual(afterVersion, beforeVersion)
})

test('test_keeps_run_version_when_other_run_changes', () => {
  // Arrange
  const before = [
    { id: 'run-1-tool', run_id: 'run-1', sequence: 4, revision: 1 },
    { id: 'run-2-tool', run_id: 'run-2', sequence: 5, revision: 1 },
  ]
  const after = [
    before[0],
    { ...before[1], sequence: 6, revision: 2 },
  ]

  // Act
  const beforeVersion = traceRunVersion(before, 'run-1')
  const afterVersion = traceRunVersion(after, 'run-1')

  // Assert
  assert.equal(afterVersion, beforeVersion)
})
