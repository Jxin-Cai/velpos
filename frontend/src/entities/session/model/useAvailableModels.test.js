import test from 'node:test'
import assert from 'node:assert/strict'

import { collectModelsWithRetry } from './collectModelsWithRetry.js'

test('test_returns_models_when_first_fetch_succeeds', async () => {
  // Arrange
  const models = [{ value: 'claude-sonnet-4', displayName: 'Sonnet' }]

  // Act
  const result = await collectModelsWithRetry(async () => models, {
    delays: [0],
    sleep: async () => {},
  })

  // Assert
  assert.deepEqual(result, models)
})

test('test_keeps_retrying_when_first_fetches_are_empty', async () => {
  // Arrange
  const models = [{ value: 'claude-opus-4', displayName: 'Opus' }]
  const fetches = [[], [], models]
  let calls = 0

  // Act
  const result = await collectModelsWithRetry(async () => fetches[calls++] || [], {
    delays: [0, 10, 10],
    sleep: async () => {},
  })

  // Assert
  assert.equal(calls, 3)
  assert.deepEqual(result, models)
})

test('test_returns_empty_list_when_all_retries_are_empty', async () => {
  // Arrange
  let calls = 0

  // Act
  const result = await collectModelsWithRetry(async () => {
    calls += 1
    return []
  }, {
    delays: [0, 10],
    sleep: async () => {},
  })

  // Assert
  assert.equal(calls, 2)
  assert.deepEqual(result, [])
})
