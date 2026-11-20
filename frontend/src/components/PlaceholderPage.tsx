import { PageHeader } from './PageHeader'

type PlaceholderPageProps = {
  title: string
  description: string
  nextStep: string
}

export function PlaceholderPage({ title, description, nextStep }: PlaceholderPageProps) {
  return (
    <>
      <PageHeader title={title} description={description} />
      <section className="placeholder-card" aria-labelledby="placeholder-title">
        <div className="placeholder-icon" aria-hidden="true">✦</div>
        <div>
          <p className="eyebrow">Phase 1 foundation</p>
          <h2 id="placeholder-title">{title} workspace is ready</h2>
          <p>This route is intentionally a placeholder. Operational workflows will be introduced after the approved API and business rules are implemented.</p>
          <div className="next-step"><strong>Planned next step</strong><span>{nextStep}</span></div>
        </div>
      </section>
    </>
  )
}