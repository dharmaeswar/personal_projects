/**
 * Consent-gated analytics: events are queued locally and only sent when the
 * visitor granted analytics consent. Batches flush every 5 seconds or when
 * 10 events pile up; a failed flush keeps the events for the next try.
 * Nothing is sent before consent — the queue is the privacy boundary.
 */

export function createAnalyticsTracker({ visitorId, send, flushIntervalMs = 5000 }) {
  let consent = false
  let queue = []
  let timer = null

  function scheduleFlush() {
    if (timer !== null || queue.length === 0) return
    timer = setTimeout(() => {
      timer = null
      flush()
    }, flushIntervalMs)
  }

  async function flush() {
    if (!consent || queue.length === 0) return
    const batch = queue
    queue = []
    try {
      await send({ visitor_id: visitorId, events: batch })
    } catch {
      queue = [...batch, ...queue] // keep events; retry on the next flush
    }
  }

  return {
    setConsent(granted) {
      consent = granted
      if (granted) scheduleFlush()
    },
    track(name, properties = {}) {
      if (!consent) return false // dropped before consent: never sent
      queue.push({ name, properties })
      if (queue.length >= 10) {
        flush()
      } else {
        scheduleFlush()
      }
      return true
    },
    flush,
    get queued() {
      return queue.length
    },
  }
}
