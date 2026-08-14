import test from 'node:test'
import assert from 'node:assert/strict'

import { buildExecutionTraceReport } from './executionTraceExport.js'

test('test_full_trace_export_contains_all_signal_and_paginated_execution_data_when_run_exists', async () => {
  // Arrange
  const rootTree = {
    agent_id: 'main',
    tasks: [{ id: 'task-1', loops: [{ id: 'loop-1' }] }],
    subagents: [{ span_id: 'agent-span-1' }],
  }
  const childTree = {
    agent_id: 'researcher',
    tasks: [{ id: 'task-2', loops: [{ id: 'loop-2' }] }],
  }

  // Act
  const report = await buildExecutionTraceReport({
    sessionId: 'session-1',
    runId: 'run-1',
    rootTree,
    fetchTree: async (_sessionId, _runId, spanId) => spanId === 'agent-span-1' ? childTree : null,
    fetchDetail: async (_sessionId, _runId, loopId) => ({
      items: [{ type: 'tool_result', content: loopId }],
      next_cursor: null,
    }),
    fetchTraceTree: async () => ({ span_count: 3, tree: [{ id: 'span-1' }] }),
    fetchTelemetrySummary: async () => ({ log_event_count: 2, metric_sample_count: 4 }),
    fetchExecutionEvents: async (_sessionId, _runId, cursor) => cursor === 0
      ? { events: [{ sequence: 1 }], next_sequence: 1, has_more: true }
      : { events: [{ sequence: 2 }], next_sequence: 2, has_more: false },
    exportedAt: '2026-08-14T00:00:00.000Z',
  })

  // Assert
  assert.equal(report.format, 'velpos.execution-trace.v2')
  assert.equal(report.summary.span_count, 3)
  assert.equal(report.summary.execution_event_count, 2)
  assert.equal(report.summary.agent_count, 2)
  assert.deepEqual(report.execution_events.map(event => event.sequence), [1, 2])
  assert.equal(report.agents[1].loop_details[0].events[0].content, 'loop-2')
})
