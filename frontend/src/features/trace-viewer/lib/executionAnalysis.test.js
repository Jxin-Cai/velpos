import test from 'node:test'
import assert from 'node:assert/strict'
import {
  ExecutionPresentation,
  buildExecutionTaskRows,
  buildSubagentChain,
  executionMetricPercent,
  executionStepTokens,
  rankExecutionTasks,
  taskSubagents,
} from './executionAnalysis.js'

function task(id, loops) {
  return { id, subject: id, loops }
}

function loop(id, durationMs, inputTokens, outputTokens, sequence) {
  return {
    id,
    sequence,
    duration_ms: durationMs,
    usage: { input_tokens: inputTokens, output_tokens: outputTokens },
  }
}

test('test_aggregates_task_duration_and_tokens_when_task_has_multiple_steps', () => {
  const [row] = buildExecutionTaskRows([
    task('task-1', [loop('one', 1200, 100, 20, 1), loop('two', 800, 50, 10, 2)]),
  ])

  assert.deepEqual(
    { duration: row.activeDurationMs, tokens: row.tokens },
    { duration: 2000, tokens: 180 },
  )
})

test('test_ranks_tasks_and_steps_by_duration_when_duration_mode_selected', () => {
  const rows = buildExecutionTaskRows([
    task('short', [loop('short-step', 100, 10, 0, 1)]),
    task('long', [loop('second', 200, 10, 0, 2), loop('first', 900, 10, 0, 1)]),
  ])

  const ranked = rankExecutionTasks(rows, ExecutionPresentation.DURATION)

  assert.deepEqual(
    [ranked[0].task.id, ranked[0].steps[0].loop.id],
    ['long', 'first'],
  )
})

test('test_ranks_tasks_and_steps_by_tokens_when_token_mode_selected', () => {
  const rows = buildExecutionTaskRows([
    task('low', [loop('low-step', 900, 10, 10, 1)]),
    task('high', [loop('less', 900, 50, 25, 1), loop('more', 100, 200, 50, 2)]),
  ])

  const ranked = rankExecutionTasks(rows, ExecutionPresentation.TOKENS)

  assert.deepEqual(
    [ranked[0].task.id, ranked[0].steps[0].loop.id],
    ['high', 'more'],
  )
})

test('test_sums_input_and_output_tokens_when_step_usage_exists', () => {
  assert.equal(executionStepTokens(loop('step', 10, 120, 30, 1)), 150)
})

test('test_uses_one_global_scale_when_step_durations_differ_across_tasks', () => {
  // Arrange
  const shortDuration = 21_000
  const longestDuration = 16 * 60_000

  // Act
  const shortPercent = executionMetricPercent(shortDuration, longestDuration)
  const longestPercent = executionMetricPercent(longestDuration, longestDuration)

  // Assert
  assert.equal(Math.round(shortPercent * 10) / 10, 2.2)
  assert.equal(longestPercent, 100)
})

test('test_lists_unique_subagents_when_task_calls_agents_across_steps', () => {
  // Arrange
  const agent = { tool_use_id: 'agent-1', span_id: 'span-1', subagent: 'Explore' }
  const source = task('task-with-agent', [
    { ...loop('one', 100, 0, 0, 1), subagents: [agent] },
    { ...loop('two', 100, 0, 0, 2), subagents: [agent] },
  ])

  // Act
  const result = taskSubagents(source)

  // Assert
  assert.deepEqual(result, [agent])
})

test('test_orders_subagents_by_invocation_when_tasks_delegate_across_steps', () => {
  // Arrange
  const explore = { tool_use_id: 'agent-1', span_id: 'span-1', subagent: 'Explore' }
  const review = { tool_use_id: 'agent-2', span_id: 'span-2', subagent: 'Review' }
  const tasks = [
    task('first', [{ ...loop('one', 100, 0, 0, 1), subagents: [explore] }]),
    task('second', [{ ...loop('two', 100, 0, 0, 2), subagents: [review] }]),
  ]

  // Act
  const chain = buildSubagentChain(tasks)

  // Assert
  assert.deepEqual(
    chain.map(item => [item.order, item.subagent, item.stepSequence]),
    [[1, 'Explore', 1], [2, 'Review', 2]],
  )
})

test('test_lists_subagent_once_when_the_same_agent_runs_in_several_steps', () => {
  // Arrange
  const agent = { tool_use_id: 'agent-1', span_id: 'span-1', subagent: 'Explore' }
  const tasks = [task('repeat', [
    { ...loop('one', 100, 0, 0, 1), subagents: [agent] },
    { ...loop('two', 100, 0, 0, 2), subagents: [agent] },
  ])]

  // Act
  const chain = buildSubagentChain(tasks)

  // Assert
  assert.deepEqual(chain.map(item => item.key), ['agent-1'])
})

test('test_appends_subagent_when_no_step_references_its_invocation', () => {
  // Arrange
  const orphan = { tool_use_id: 'agent-9', span_id: 'span-9', subagent: 'Detached' }

  // Act
  const chain = buildSubagentChain([task('empty', [loop('one', 100, 0, 0, 1)])], [orphan])

  // Assert
  assert.deepEqual(
    chain.map(item => [item.key, item.stepSequence]),
    [['agent-9', null]],
  )
})
