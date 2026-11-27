import { useCallback, useEffect, useState } from 'react'
import { PageHeader } from '../components/PageHeader'
import { useAuth } from '../auth/useAuth'
import './workflows.css'

type Approval = { id: string; entity_type: string; entity_id: string; required_capability: string; created_at: string }

export function OperationalApprovalsPage() {
  const { session } = useAuth()
  const [items, setItems] = useState<Approval[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const refresh = useCallback(async () => {
    setError('')
    try {
      const response = await fetch('/api/v1/inventory/workflow-approvals', { credentials: 'same-origin', cache: 'no-store', headers: { Accept: 'application/json' } })
      if (!response.ok) throw new Error()
      setItems(await response.json() as Approval[])
    } catch { setItems(null); setError('The protected approval queue is unavailable. No preview requests were substituted.') }
  }, [])
  useEffect(() => { void refresh() }, [refresh])
  async function decide(item: Approval, decision: 'approved' | 'rejected') {
    if (!session?.csrfToken) { setError('A confirmed session is required.'); return }
    setBusy(true); setError(''); setNotice('')
    try {
      const response = await fetch(`/api/v1/inventory/workflow-approvals/${item.id}/decision`, {
        method: 'POST', credentials: 'same-origin', cache: 'no-store',
        headers: { Accept: 'application/json', 'Content-Type': 'application/json', 'X-CSRF-Token': session.csrfToken },
        body: JSON.stringify({ decision }),
      })
      if (!response.ok) throw new Error()
      setNotice(`The ${item.entity_type.replaceAll('_', ' ')} request was ${decision}.`)
      await refresh()
    } catch { setError('The decision was not confirmed. The server enforces current permission, scope and the configured single-approval rules.') }
    finally { setBusy(false) }
  }
  return <main className="page-content">
    <PageHeader eyebrow="Authenticated inventory" title="Approvals" description="Only explicit decisions by a currently authorized approver are accepted." />
    <section className="workflow-panel"><h2>Pending decisions</h2>
      {items?.map((item) => <article className="workflow-list-item" key={item.id}>
        <strong>{item.entity_type.replaceAll('_', ' ')}</strong><span>{item.entity_id}</span><small>{item.required_capability}</small>
        <button className="button workflow-secondary" disabled={busy || !session?.csrfToken} onClick={() => void decide(item, 'approved')}>Approve</button>
        <button className="button workflow-secondary" disabled={busy || !session?.csrfToken} onClick={() => void decide(item, 'rejected')}>Reject</button>
      </article>)}
      {items?.length === 0 && <p>No pending approval requests.</p>}
      {items === null && <button className="button workflow-secondary" onClick={() => void refresh()}>Retry</button>}
    </section>
    {error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
  </main>
}
