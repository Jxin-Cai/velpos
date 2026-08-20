export const MODEL_RETRY_DELAYS_MS = [0, 1200, 2500, 4000]

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms))
}

export async function collectModelsWithRetry(fetchModels, {
  delays = MODEL_RETRY_DELAYS_MS,
  sleep: sleepFn = sleep,
  isStale = () => false,
} = {}) {
  for (const delay of delays) {
    if (delay) await sleepFn(delay)
    if (isStale()) return null
    try {
      const models = (await fetchModels()) || []
      if (isStale()) return null
      if (models.length) return models
    } catch {
      if (isStale()) return null
    }
  }
  return []
}
