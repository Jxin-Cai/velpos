import test from 'node:test'
import assert from 'node:assert/strict'
import {
  TracePresentation,
  annotateTraceConcurrency,
  buildTraceAnalysis,
  buildSubagentRoster,
  countSubagentInvocations,
  filterTraceTree,
  isSubagentTraceSpan,
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

test('test_recognizes_official_agent_tool_span_when_subagent_type_is_not_emitted', () => {
  // Arrange
  const span = {
    id: 'agent-tool-span',
    span_type: 'tool_call',
    name: 'Agent',
    tool_use_id: 'call-agent-1',
    metadata: { 'telemetry.source': 'claude_code_otel' },
  }

  // Act / Assert
  assert.equal(isSubagentTraceSpan(span), true)
})

test('test_deduplicates_tool_and_dedicated_span_when_both_describe_same_subagent', () => {
  // Arrange
  const spans = [
    { id: 'tool', span_type: 'tool_call', name: 'Agent', tool_use_id: 'call-agent-1', metadata: {} },
    { id: 'agent', span_type: 'subagent', name: 'Explore', tool_use_id: 'call-agent-1', metadata: {} },
  ]

  // Act / Assert
  assert.equal(countSubagentInvocations(spans), 1)
})

test('test_builds_clickable_subagent_roster_from_official_agent_tool_spans', () => {
  // Arrange
  const spans = [{
    id: 'agent-span-1',
    span_type: 'tool_call',
    name: 'Agent',
    tool_use_id: 'call-agent-1',
    status: 'completed',
    duration_ms: 4200,
    metadata: { subagent_type: 'Explore' },
  }]

  // Act
  const roster = buildSubagentRoster(spans)

  // Assert
  assert.deepEqual(roster, [{
    key: 'call-agent-1',
    tool_use_id: 'call-agent-1',
    span_id: 'agent-span-1',
    subagent: 'Explore',
    status: 'completed',
    duration_ms: 4200,
    is_expandable: true,
  }])
})

test('test_keeps_official_agent_tool_when_subagent_filter_selected', () => {
  // Arrange
  const source = [{ id: 'run', span_type: 'run', children: [
    { id: 'agent-tool', span_type: 'tool_call', name: 'Agent', metadata: { subagent_type: 'Explore' }, children: [] },
    { id: 'bash-tool', span_type: 'tool_call', name: 'Bash', metadata: {}, children: [] },
  ] }]

  // Act
  const filtered = filterTraceTree(source, 'subagents', 0)

  // Assert
  assert.deepEqual(filtered[0].children.map(child => child.id), ['agent-tool'])
})
