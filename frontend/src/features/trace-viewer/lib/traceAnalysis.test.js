import test from 'node:test'
import assert from 'node:assert/strict'
import {
  TracePresentation,
  annotateTraceConcurrency,
  buildTraceAnalysis,
  filterTraceTree,
  rankTraceRows,
  spanSelfDuration,
  spanTokenCount,
} from './traceAnalysis.js'

const tree = [{
  id: 'run', span_type: 'run', duration_ms: 1000, children: [
    { id: 'fast', span_type: 'llm_turn', duration_ms: 100, metadata: { input_tokens: 10, output_tokens: 5 }, children: [] },
    { id: 'slow', span_type: 'tool_call', duration_ms: 900, status: 'failed', metadata: {}, children: [] },
    { id: 'tokens', span_type: 'llm_turn', duration_ms: 300, metadata: { input_tokens: 100, output_tokens: 50 }, children: [] },
    { id: 'mid', span_type: 'hook', duration_ms: 200, metadata: {}, children: [] },
  ],
}]

test('test_ranks_actionable_spans_by_duration_when_duration_view_selected', () => {
  const analysis = buildTraceAnalysis(tree)

  const ranked = rankTraceRows(analysis.rows, TracePresentation.DURATION)

  assert.deepEqual(ranked.map(row => row.span.id), ['slow', 'tokens', 'mid', 'fast'])
})

test('test_ranks_only_token_consuming_spans_when_token_view_selected', () => {
  const analysis = buildTraceAnalysis(tree)

  const ranked = rankTraceRows(analysis.rows, TracePresentation.TOKENS)

  assert.deepEqual(ranked.map(row => row.span.id), ['tokens', 'fast'])
})

test('test_marks_trace_local_p90_span_as_hot_when_duration_distribution_exists', () => {
  const analysis = buildTraceAnalysis(tree)

  const slow = analysis.rows.find(row => row.span.id === 'slow')

  assert.equal(analysis.thresholds.p90, 900)
  assert.equal(slow.durationBand, 'hot')
})

test('test_keeps_only_matches_and_ancestors_when_error_filter_selected', () => {
  const filtered = filterTraceTree(tree, 'errors', 0)

  assert.equal(filtered[0].id, 'run')
  assert.deepEqual(filtered[0].children.map(child => child.id), ['slow'])
})

test('test_sums_input_and_output_tokens_when_span_has_usage', () => {
  assert.equal(spanTokenCount(tree[0].children[0]), 15)
})

test('test_excludes_overlapping_child_time_when_parent_self_duration_calculated', () => {
  const span = {
    duration_ms: 1000,
    started_time: '2026-08-14T00:00:00.000Z',
    children: [
      { started_time: '2026-08-14T00:00:00.100Z', ended_time: '2026-08-14T00:00:00.600Z' },
      { started_time: '2026-08-14T00:00:00.400Z', ended_time: '2026-08-14T00:00:00.800Z' },
    ],
  }

  assert.equal(spanSelfDuration(span), 300)
})

test('test_infers_nested_tool_time_when_compatibility_span_parent_is_missing', () => {
  const turn = { id: 'turn', span_type: 'llm_turn', duration_ms: 1000, started_time: '2026-08-14T00:00:00.000Z' }
  const tool = { id: 'tool', span_type: 'tool_call', duration_ms: 700, started_time: '2026-08-14T00:00:00.200Z', ended_time: '2026-08-14T00:00:00.900Z' }

  assert.equal(spanSelfDuration(turn, [turn, tool]), 300)
  assert.equal(spanSelfDuration(tool, [turn, tool]), 700)
})

test('test_marks_overlapping_sibling_spans_as_parallel_when_intervals_overlap', () => {
  const result = annotateTraceConcurrency([{
    id: 'root',
    started_time: '2026-08-14T10:00:00Z',
    ended_time: '2026-08-14T10:00:10Z',
    children: [
      { id: 'left', started_time: '2026-08-14T10:00:01Z', ended_time: '2026-08-14T10:00:06Z', children: [] },
      { id: 'right', started_time: '2026-08-14T10:00:02Z', ended_time: '2026-08-14T10:00:05Z', children: [] },
    ],
  }])

  assert.deepEqual(
    [result.groupCount, result.maxConcurrency, result.tree[0].children[0].parallelGroup.peak],
    [1, 2, 2],
  )
})
