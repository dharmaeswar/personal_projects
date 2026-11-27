/** Renders a content page fetched from the API: hero block first, then text blocks. */
export default function PageContent({ page }) {
  if (!page) return <p>Loading…</p>
  return (
    <main>
      <h1>{page.title}</h1>
      {page.blocks.map((block, i) => (
        <section key={i}>
          <h2>{block.heading}</h2>
          <p>{block.body}</p>
        </section>
      ))}
    </main>
  )
}
