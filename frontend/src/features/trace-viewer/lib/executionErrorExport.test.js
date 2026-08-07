import test from 'node:test'
import assert from 'node:assert/strict'

import { buildExecutionErrorReport } from './executionErrorExport.js'

test('test_download_report_contains_full_paginated_error_context_when_step_failed', async () => {
  // Arrange
  const rootTree = {
    agent_id: 'main',
    error_message: 'Plugin execution failed',
    provenance: { completeness: 'complete' },
    tasks: [{
      id: 'task-1',
      subject: 'Run plugin',
      status: 'failed',
      loops: [{
        id: 'loop-1',
        sequence: 1,
        tool_names: ['plugin.tool'],
        error_count: 1,
        error_message: 'Invalid plugin response',
        error_summary: { total: 1, failed_tools: ['plugin.tool'] },
      }],
    }],
  }
  const requestedCursors = []
  const fetchDetail = async (_sessionId, _runId, _loopId, _agentSpanId, cursor, limit) => {
    requestedCursors.push({ cursor, limit })
    return cursor === 0
      ? { items: [
        { type: 'model_input', content: 'unrelated conversation context' },
        { type: 'tool_use', tool_use_id: 'tool-1', content: { input: true } },
      ], next_cursor: 1 }
      : { items: [{ type: 'tool_result', tool_use_id: 'tool-1', is_error: true, error_message: 'boom' }], next_cursor: null }
  }

  // Act
  const report = await buildExecutionErrorReport({
    sessionId: 'session-1',
    runId: 'run-1',
    rootTree,
    fetchTree: async () => null,
    fetchDetail,
    exportedAt: '2026-08-07T00:00:00.000Z',
  })

  // Assert
  assert.deepEqual(report, {
    format: 'velpos.execution-errors.v1',
    session_id: 'session-1',
    run_id: 'run-1',
    exported_at: '2026-08-07T00:00:00.000Z',
    summary: { error_count: 2, error_step_count: 1, scanned_agent_count: 1 },
    run_error: 'Plugin execution failed',
    provenance: { completeness: 'complete' },
    errors: [{
      agent_id: 'main',
      agent_span_id: null,
      task: { id: 'task-1', subject: 'Run plugin', description: null, status: 'failed' },
      step: {
        id: 'loop-1', sequence: 1, model: null, tool_names: ['plugin.tool'],
        started_time: null, ended_time: null, duration_ms: 0,
        error_message: 'Invalid plugin response', error_count: 1,
        error_summary: { total: 1, failed_tools: ['plugin.tool'] },
      },
      events: [
        { type: 'tool_use', tool_use_id: 'tool-1', content: { input: true } },
        { type: 'tool_result', tool_use_id: 'tool-1', is_error: true, error_message: 'boom' },
      ],
      error_events: [
        { type: 'tool_result', tool_use_id: 'tool-1', is_error: true, error_message: 'boom' },
      ],
    }],
  })
  assert.deepEqual(requestedCursors, [{ cursor: 0, limit: 500 }, { cursor: 1, limit: 500 }])
})

test('test_download_report_includes_subagent_errors_when_nested_agent_failed', async () => {
  // Arrange
  const rootTree = {
    agent_id: 'main',
    tasks: [],
    subagents: [{ span_id: 'agent-span-1' }],
  }
  const childTree = {
    agent_id: 'researcher',
    tasks: [{
      id: 'child-task',
      subject: 'Inspect plugin',
      status: 'failed',
      loops: [{ id: 'child-loop', sequence: 1, error_count: 1, error_message: 'Child failure' }],
    }],
  }

  // Act
  const report = await buildExecutionErrorReport({
    sessionId: 'session-1',
    runId: 'run-1',
    rootTree,
    fetchTree: async (_sessionId, _runId, spanId) => spanId === 'agent-span-1' ? childTree : null,
    fetchDetail: async () => ({
      items: [{ type: 'tool_result', is_error: true, error_message: 'Child failure' }],
      next_cursor: null,
    }),
  })

  // Assert
  assert.equal(report.errors[0].agent_span_id, 'agent-span-1')
  assert.equal(report.errors[0].error_events[0].error_message, 'Child failure')
})
