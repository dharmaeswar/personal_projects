import { describe, it, expect, vi } from 'vitest'
import { createAnalyticsTracker } from '../lib/analytics'

describe('consent-gated analytics tracker', () => {
  it('drops events tracked before consent', () => {
    const send = vi.fn().mockResolvedValue({})
    const tracker = createAnalyticsTracker({ visitorId: 'v-1', send })
    expect(tracker.track('page_view')).toBe(false)
    expect(tracker.queued).toBe(0)
    expect(send).not.toHaveBeenCalled()
  })

  it('queues events after consent and flushes them in one batch', async () => {
    const send = vi.fn().mockResolvedValue({})
    const tracker = createAnalyticsTracker({ visitorId: 'v-1', send })
    tracker.setConsent(true)
    expect(tracker.track('page_view', { path: '/' })).toBe(true)
    tracker.track('cta_click', { id: 'signup' })
    await tracker.flush()
    expect(send).toHaveBeenCalledTimes(1)
    expect(send.mock.calls[0][0].events).toHaveLength(2)
    expect(tracker.queued).toBe(0)
  })

  it('keeps events when a flush fails so they can be retried', async () => {
    const send = vi.fn().mockRejectedValueOnce(new Error('down'))
    const tracker = createAnalyticsTracker({ visitorId: 'v-1', send })
    tracker.setConsent(true)
    tracker.track('page_view')
    await tracker.flush()
    expect(tracker.queued).toBe(1)
    send.mockResolvedValueOnce({})
    await tracker.flush()
    expect(tracker.queued).toBe(0)
  })

  it('does not flush while consent is off even with queued events', async () => {
    const send = vi.fn().mockResolvedValue({})
    const tracker = createAnalyticsTracker({ visitorId: 'v-1', send })
    tracker.setConsent(true)
    tracker.track('page_view')
    tracker.setConsent(false)
    await tracker.flush()
    expect(send).not.toHaveBeenCalled()
  })
})
