import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { PageHeader } from '../components/PageHeader'
import { useAuth } from '../auth/useAuth'
import './workflows.css'

type Kind = 'repairs' | 'disposals' | 'exit-clearance'
type Row = Record<string, unknown> & { id: string; status: string }
const DISPOSAL_REASONS = [
  ['damaged_beyond_repair', 'Damaged beyond repair'],
  ['obsolete', 'Obsolete'],
  ['end_of_useful_life', 'End of useful life'],
  ['uneconomical_repair', 'Uneconomical repair'],
] as const
const REPAIR_CURRENCIES = ['LKR', 'GBP', 'USD', 'EUR'] as const

async function getRows(path: string): Promise<Row[]> {
  const response = await fetch(`/api/v1/inventory/${path}`, { credentials: 'same-origin', cache: 'no-store', headers: { Accept: 'application/json' } })
  if (!response.ok) throw new Error('Operational workflow data is unavailable.')
  return response.json() as Promise<Row[]>
}

export function OperationalLifecyclePage({ kind }: { kind: Kind }) {
  const { session } = useAuth()
  const [rows, setRows] = useState<Row[] | null>(null)
  const [identifier, setIdentifier] = useState('')
  const [reason, setReason] = useState('')
  const [details, setDetails] = useState('')
  const [provider, setProvider] = useState('')
  const [completionCondition, setCompletionCondition] = useState<'good' | 'damaged'>('good')
  const [completionNotes, setCompletionNotes] = useState('')
  const [costAmount, setCostAmount] = useState('')
  const [costCurrency, setCostCurrency] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const resource = kind === 'exit-clearance' ? 'exit-clearances' : kind
  const refresh = useCallback(async () => {
    setError('')
    try { setRows(await getRows(resource)) }
    catch { setRows(null); setError('The protected workflow service is unavailable. No preview records were substituted.') }
  }, [resource])
  useEffect(() => { void refresh() }, [refresh])

  async function post(path: string, body: unknown = {}, idempotent = false) {
    if (!session?.csrfToken) throw new Error('A confirmed session is required.')
    const response = await fetch(`/api/v1/inventory/${path}`, {
      method: 'POST', credentials: 'same-origin', cache: 'no-store',
      headers: { Accept: 'application/json', 'Content-Type': 'application/json', 'X-CSRF-Token': session.csrfToken,
        ...(idempotent ? { 'Idempotency-Key': crypto.randomUUID() } : {}) },
      body: JSON.stringify(body),
    })
    if (!response.ok) throw new Error('The operation could not be confirmed by the server.')
  }

  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(''); setNotice('')
    try {
      if (kind === 'repairs') await post(`assets/${identifier}/repairs`, { issue_details: details, repair_provider: provider || null }, true)
      else if (kind === 'disposals') await post(`assets/${identifier}/disposals`, { reason_code: reason }, true)
      else await post(`employees/${identifier}/exit-clearances`)
      setNotice('The request was recorded and is awaiting an explicit approval decision.')
      setIdentifier(''); setDetails(''); setProvider(''); setReason(''); await refresh()
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'The request was not confirmed.') }
    finally { setBusy(false) }
  }

  async function action(row: Row, actionName: string, body: unknown = {}) {
    setBusy(true); setError(''); setNotice('')
    try { await post(`${resource}/${row.id}/${actionName}`, body); setNotice('The server confirmed the workflow update.'); await refresh() }
    catch (failure) { setError(failure instanceof Error ? failure.message : 'The workflow update was not confirmed.') }
    finally { setBusy(false) }
  }

  const title = kind === 'repairs' ? 'Repairs' : kind === 'disposals' ? 'Disposal' : 'Employee exit clearance'
  return <main className="page-content">
    <PageHeader eyebrow="Authenticated inventory" title={title} description="Requests are persisted only after server-side authorization, workflow checks and audit recording." />
    <section className="workflow-panel">
      <h2>{kind === 'repairs' ? 'Open repair case' : kind === 'disposals' ? 'Request asset disposal' : 'Open clearance case'}</h2>
      <form className="workflow-form" onSubmit={(event) => void submit(event)}>
        <label>{kind === 'exit-clearance' ? 'Employee ID' : 'Asset ID'}<input required value={identifier} onChange={(event) => setIdentifier(event.target.value)} /></label>
        {kind === 'repairs' && <><label>Issue details<textarea required maxLength={4000} value={details} onChange={(event) => setDetails(event.target.value)} /></label><label>Repair provider<input maxLength={200} value={provider} onChange={(event) => setProvider(event.target.value)} /></label></>}
        {kind === 'disposals' && <label>Disposal reason<select required value={reason} onChange={(event) => setReason(event.target.value)}><option value="">Select a reason</option>{DISPOSAL_REASONS.map(([code, label]) => <option key={code} value={code}>{label}</option>)}</select></label>}
        <button className="button button-primary" disabled={busy || !session?.csrfToken}>Submit request</button>
      </form>
    </section>
    <section className="workflow-panel"><h2>Workflow history</h2>
      {rows?.map((row) => <article className="workflow-list-item" key={row.id}>
        <strong>{row.id}</strong><span>{row.status}{typeof row.verification_status === 'string' ? ` · ${row.verification_status}` : ''}</span>
        {kind === 'repairs' && row.status === 'in_progress' && <div className="workflow-form">
          <label>Completion condition<select value={completionCondition} onChange={(event) => setCompletionCondition(event.target.value as 'good' | 'damaged')}><option value="good">Good, return to available</option><option value="damaged">Still damaged</option></select></label>
          <label>Completion notes<textarea maxLength={4000} value={completionNotes} onChange={(event) => setCompletionNotes(event.target.value)} /></label>
          <label>Repair cost<input type="number" min="0" step="0.01" value={costAmount} onChange={(event) => setCostAmount(event.target.value)} /></label>
          <label>Currency<select value={costCurrency} onChange={(event) => setCostCurrency(event.target.value)}><option value="">Select a currency</option>{REPAIR_CURRENCIES.map((currency) => <option key={currency} value={currency}>{currency}</option>)}</select></label>
          <button className="button workflow-secondary" disabled={busy || (!costAmount && !!costCurrency) || (!!costAmount && !costCurrency)} onClick={() => void action(row, 'complete', { condition: completionCondition, notes: completionNotes || null, cost_amount: costAmount || null, cost_currency: costCurrency || null })}>Record repair completion</button>
        </div>}
        {kind === 'disposals' && row.status === 'approved' && <button className="button workflow-secondary" disabled={busy} onClick={() => void action(row, 'finalize')}>Finalize approved disposal</button>}
        {kind === 'exit-clearance' && row.status !== 'completed' && <><button className="button workflow-secondary" disabled={busy} onClick={() => void action(row, 'verify')}>Verify clearance</button><button className="button workflow-secondary" disabled={busy} onClick={() => void action(row, 'complete')}>Complete clearance</button><button className="button workflow-secondary" disabled={busy} onClick={() => void action(row, 'cancel')}>Cancel</button></>}
      </article>)}
      {rows?.length === 0 && <p>No workflow records are available.</p>}
      {rows === null && <button className="button workflow-secondary" onClick={() => void refresh()}>Retry</button>}
    </section>
    {error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
  </main>
}
