// Claude's transcript carries no telemetry event id, so a projected step and the
// raw request body that produced it can only be related through time. Requests
// are logged as the step is dispatched, which makes the step's start the anchor.
const MATCH_TOLERANCE_MS = 30000

function toEpoch(value) {
  if (!value) return null
  const parsed = Date.parse(value)
  return Number.isNaN(parsed) ? null : parsed
}

/**
 * Pair each step with the provider request that most likely produced it.
 *
 * Both sides are chronological, so candidates are consumed in order and never
 * reused: one request describes exactly one step.
 *
 * @param {Array<{id: string, started_time?: string, ended_time?: string}>} loops
 * @param {Array<{event_id: string, event_time?: string}>} requests
 * @returns {Map<string, object>} step id to request summary
 */
export function matchRequestsToLoops(loops, requests) {
  const matches = new Map()
  if (!Array.isArray(loops) || !Array.isArray(requests) || requests.length === 0) return matches

  const candidates = requests
    .map(request => ({ request, at: toEpoch(request?.event_time) }))
    .filter(entry => entry.at != null)
    .sort((left, right) => left.at - right.at)

  const used = new Set()
  const anchoredLoops = loops
    .map(loop => ({ loop, at: toEpoch(loop?.started_time) ?? toEpoch(loop?.ended_time) }))
    .filter(entry => entry.at != null)
    .sort((left, right) => left.at - right.at)

  for (const { loop, at } of anchoredLoops) {
    let best = null
    let bestDistance = Infinity
    for (let index = 0; index < candidates.length; index += 1) {
      if (used.has(index)) continue
      const distance = Math.abs(candidates[index].at - at)
      if (distance < bestDistance) {
        bestDistance = distance
        best = index
      }
    }
    if (best != null && bestDistance <= MATCH_TOLERANCE_MS) {
      used.add(best)
      matches.set(loop.id, candidates[best].request)
    }
  }

  return matches
}

export const MATCH_TOLERANCE = MATCH_TOLERANCE_MS
