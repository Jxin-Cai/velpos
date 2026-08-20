import { ref } from 'vue'
import { listModels } from '../api/sessionApi'
import { collectModelsWithRetry } from './collectModelsWithRetry.js'

const availableModels = ref([])
const modelsLoading = ref(false)
const modelsSettled = ref(false)

let inFlight = null
let seq = 0

export async function loadAvailableModels({ force = false } = {}) {
  if (!force && availableModels.value.length) return inFlight
  if (!force && inFlight) return inFlight

  const current = ++seq
  modelsLoading.value = true
  if (!availableModels.value.length) {
    modelsSettled.value = false
  }

  inFlight = (async () => {
    try {
      const models = await collectModelsWithRetry(listModels, {
        isStale: () => current !== seq,
      })
      if (current !== seq || models == null) return
      availableModels.value = models
    } finally {
      if (current === seq) {
        modelsLoading.value = false
        modelsSettled.value = true
        inFlight = null
      }
    }
  })()

  return inFlight
}

export function beginModelsLoading() {
  if (availableModels.value.length) return
  modelsLoading.value = true
  modelsSettled.value = false
}

export function useAvailableModels() {
  return {
    availableModels,
    modelsLoading,
    modelsSettled,
    loadAvailableModels,
    beginModelsLoading,
  }
}
