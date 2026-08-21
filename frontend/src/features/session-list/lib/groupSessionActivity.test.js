import test from 'node:test'
import assert from 'node:assert/strict'

import { groupActivityLabel, summarizeGroupSessionActivity } from './groupSessionActivity.js'

test('test_reports_running_when_any_session_is_executing', () => {
  const activity = summarizeGroupSessionActivity([
    { session_id: 's1', status: 'running', source: 'velpos' },
  ])

  assert.deepEqual(activity, { hasRunning: true, hasUnviewedCompleted: false })
})

test('test_ignores_viewed_idle_sessions_on_the_directory', () => {
  const activity = summarizeGroupSessionActivity([
    { session_id: 's1', status: 'idle', source: 'velpos' },
  ])

  assert.deepEqual(activity, { hasRunning: false, hasUnviewedCompleted: false })
})

test('test_reports_unviewed_when_idle_session_has_not_been_opened', () => {
  const activity = summarizeGroupSessionActivity(
    [{ session_id: 's1', status: 'idle', source: 'velpos' }],
    new Set(['s1']),
  )

  assert.deepEqual(activity, { hasRunning: false, hasUnviewedCompleted: true })
})

test('test_reports_both_when_group_has_running_and_unviewed_sessions', () => {
  const activity = summarizeGroupSessionActivity(
    [
      { session_id: 's1', status: 'running', source: 'velpos' },
      { session_id: 's2', status: 'idle', source: 'velpos' },
    ],
    new Set(['s2']),
  )

  assert.deepEqual(activity, { hasRunning: true, hasUnviewedCompleted: true })
})

test('test_treats_reconnecting_as_running', () => {
  const activity = summarizeGroupSessionActivity([
    { session_id: 's1', status: 'reconnecting', source: 'velpos' },
  ])

  assert.equal(activity.hasRunning, true)
})

test('test_treats_compacting_as_running', () => {
  const activity = summarizeGroupSessionActivity([
    { session_id: 's1', status: 'compacting', source: 'velpos' },
  ])

  assert.equal(activity.hasRunning, true)
})

test('test_ignores_claude_code_sessions', () => {
  const activity = summarizeGroupSessionActivity(
    [{ session_id: 's1', status: 'idle', source: 'claude-code' }],
    new Set(['s1']),
  )

  assert.deepEqual(activity, { hasRunning: false, hasUnviewedCompleted: false })
})

test('test_joins_running_and_unviewed_labels', () => {
  const label = groupActivityLabel({ hasRunning: true, hasUnviewedCompleted: true })

  assert.equal(label, 'running, unviewed')
})
