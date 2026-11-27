import { useState } from 'react'

/** Consent banner: analytics stays off until the visitor explicitly accepts. */
export default function ConsentBanner({ onChoose }) {
  const [decided, setDecided] = useState(false)
  if (decided) return null
  function choose(analytics) {
    setDecided(true)
    onChoose({ analytics, marketing: false })
  }
  return (
    <div role="region" aria-label="Cookie consent">
      <p>We use analytics to understand how this site is used.</p>
      <button type="button" onClick={() => choose(true)}>Accept analytics</button>
      <button type="button" onClick={() => choose(false)}>Decline</button>
    </div>
  )
}
