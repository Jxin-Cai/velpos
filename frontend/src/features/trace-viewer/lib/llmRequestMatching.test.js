import assert from 'node:assert/strict'
import test from 'node:test'

import { matchRequestsToLoops } from './llmRequestMatching.js'

const loop = (id, startedTime) => ({ id, started_time: startedTime })
const request = (eventId, eventTime) => ({ event_id: eventId, event_time: eventTime })

test('test_pairs_step_with_request_when_request_is_logged_at_step_start', () => {
  // Arrange
  const loops = [loop('loop-1', '2026-08-19T12:00:00Z')]
  const requests = [request('e1', '2026-08-19T12:00:01Z')]

  // Act
  const matches = matchRequestsToLoops(loops, requests)

  // Assert
  assert.equal(matches.get('loop-1').event_id, 'e1')
})

test('test_assigns_each_request_once_when_steps_run_back_to_back', () => {
  // Arrange
  const loops = [loop('loop-1', '2026-08-19T12:00:00Z'), loop('loop-2', '2026-08-19T12:00:20Z')]
  const requests = [request('e1', '2026-08-19T12:00:01Z'), request('e2', '2026-08-19T12:00:21Z')]

  // Act
  const matches = matchRequestsToLoops(loops, requests)

  // Assert
  assert.deepEqual(
    [matches.get('loop-1').event_id, matches.get('loop-2').event_id],
    ['e1', 'e2'],
  )
})

test('test_leaves_step_unmatched_when_no_request_falls_inside_tolerance', () => {
  // Arrange
  const loops = [loop('loop-1', '2026-08-19T12:00:00Z')]
  const requests = [request('e1', '2026-08-19T13:00:00Z')]

  // Act
  const matches = matchRequestsToLoops(loops, requests)

  // Assert
  assert.equal(matches.has('loop-1'), false)
})

test('test_anchors_on_step_end_when_step_has_no_start_time', () => {
  // Arrange
  const loops = [{ id: 'loop-1', ended_time: '2026-08-19T12:00:05Z' }]
  const requests = [request('e1', '2026-08-19T12:00:00Z')]

  // Act
  const matches = matchRequestsToLoops(loops, requests)

  // Assert
  assert.equal(matches.get('loop-1').event_id, 'e1')
})

test('test_skips_step_when_it_carries_no_usable_timestamp', () => {
  // Arrange
  const loops = [{ id: 'loop-1' }]
  const requests = [request('e1', '2026-08-19T12:00:00Z')]

  // Act
  const matches = matchRequestsToLoops(loops, requests)

  // Assert
  assert.equal(matches.size, 0)
})

test('test_returns_no_matches_when_run_recorded_no_request_bodies', () => {
  // Arrange
  const loops = [loop('loop-1', '2026-08-19T12:00:00Z')]

  // Act
  const matches = matchRequestsToLoops(loops, [])

  // Assert
  assert.equal(matches.size, 0)
})
