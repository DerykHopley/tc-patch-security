// The Dashboard, Settings and Dev pages are empty until their tickets fill them; the shell is what A02 builds.

export function EmptyPage({ title, comingWith }: { title: string; comingWith: string }) {
  return (
    <div className="page">
      <section className="card" aria-labelledby="page-card-title">
        <h2 id="page-card-title">{title}</h2>
        <p>Nothing here yet: this page arrives with {comingWith}.</p>
      </section>
    </div>
  )
}
