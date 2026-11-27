import { PageHeader } from './PageHeader'

export function OperationalModuleUnavailable({ module }: { module: string }) {
  return <>
    <PageHeader eyebrow="Operational service unavailable" title={module}
      description="This module is not connected to an authorized operational service." />
    <section className="panel" role="status" aria-live="polite">
      <h2>Unavailable</h2>
      <p>No preview or fictional records are shown in the authenticated workspace. The operation remains disabled until its backend, approval, audit, and authorization requirements are verified.</p>
    </section>
  </>
}
