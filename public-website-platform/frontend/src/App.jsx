import { useEffect, useState } from 'react'
import { fetchPage, fetchConsent, saveConsent } from './lib/api'
import { createAnalyticsTracker } from './lib/analytics'
import ConsentBanner from './components/ConsentBanner'
import ContactForm from './components/ContactForm'
import PageContent from './components/PageContent'

const VISITOR_ID = 'visitor-demo-1'

export default function App() {
  const [page, setPage] = useState(null)
  const [tracker] = useState(() =>
    createAnalyticsTracker({
      visitorId: VISITOR_ID,
      send: (payload) =>
        fetch('/api/analytics/events', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        }),
    }),
  )

  useEffect(() => {
    fetchPage('home').then(setPage).catch(() => setPage(null))
    fetchConsent(VISITOR_ID)
      .then((consent) => tracker.setConsent(consent.analytics))
      .catch(() => tracker.setConsent(false))
  }, [tracker])

  useEffect(() => {
    if (page) tracker.track('page_view', { path: '/' })
  }, [page, tracker])

  async function handleConsent(consent) {
    await saveConsent(VISITOR_ID, consent)
    tracker.setConsent(consent.analytics)
  }

  return (
    <>
      <ConsentBanner onChoose={handleConsent} />
      <PageContent page={page} />
      <ContactForm
        onSubmitted={() => tracker.track('form_submit', { form_id: 'contact' })}
      />
    </>
  )
}
