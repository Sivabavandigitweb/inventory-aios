import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { PageHeader } from '../components/PageHeader'
import type { TransactionApi, AllocationRow, ReturnRow, EmployeeOption, AssetOption, BalanceOption } from './apiTransactionProvider'
import './workflows.css'

type Snapshot = { employees: EmployeeOption[]; assets: AssetOption[]; balances: BalanceOption[]; allocations: AllocationRow[]; returns: ReturnRow[] }

export function OperationalTransactionsPage({ api, csrfToken }: { api: TransactionApi; csrfToken: string }) {
  const [data, setData] = useState<Snapshot | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [employee, setEmployee] = useState('')
  const [targetKind, setTargetKind] = useState<'asset' | 'quantity'>('asset')
  const [target, setTarget] = useState('')
  const [quantity, setQuantity] = useState('1')
  const [returnLine, setReturnLine] = useState('')
  const [returnQuantity, setReturnQuantity] = useState('1')
  const [condition, setCondition] = useState('good')

  const refresh = useCallback(async () => {
    setLoading(true); setError('')
    try {
      const [employees, assets, balances, allocations, returns] = await Promise.all([
        api.employees(), api.assets(), api.balances(), api.allocations(), api.returns(),
      ])
      setData({ employees, assets, balances, allocations, returns })
    } catch {
      setData(null); setError('Operational inventory data is unavailable. No preview data was substituted.')
    } finally { setLoading(false) }
  }, [api])
  useEffect(() => { void refresh() }, [refresh])

  const submitAllocation = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setError(''); setNotice('')
    try {
      const body: Record<string, string> = { employee_id: employee }
      if (targetKind === 'asset') { body.tracked_asset_id = target; body.quantity = '1' }
      else {
        const balance = data?.balances.find((item) => `${item.product_id}|${item.location_id}|${item.unit}` === target)
        if (!balance) throw new Error('Select an available quantity balance.')
        Object.assign(body, { product_id: balance.product_id, location_id: balance.location_id, unit: balance.unit, quantity })
      }
      await api.createAllocation(body, csrfToken)
      setNotice('Allocation request submitted and pending explicit approval.')
      await refresh()
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Allocation request could not be confirmed.') }
    finally { setBusy(false) }
  }
  const submitReturn = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setError(''); setNotice('')
    try {
      await api.createReturn({ allocation_line_id: returnLine, quantity: returnQuantity, condition }, csrfToken)
      setNotice('Return recorded and pending explicit verification.')
      await refresh()
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Return could not be confirmed.') }
    finally { setBusy(false) }
  }
  const decide = async (kind: 'allocation' | 'return', id: string, decision: 'approved' | 'rejected') => {
    setBusy(true); setError(''); setNotice('')
    try {
      if (kind === 'allocation') await api.decideAllocation(id, decision, csrfToken)
      else await api.decideReturn(id, decision, csrfToken)
      setNotice(`Request ${decision}.`); await refresh()
    } catch { setError('The decision could not be confirmed. Check your access and retry after reviewing the current record.') }
    finally { setBusy(false) }
  }
  const issue = async (id: string) => {
    setBusy(true); setError(''); setNotice('')
    try { await api.issueAllocation(id, csrfToken); setNotice('Approved allocation issued.'); await refresh() }
    catch { setError('Allocation could not be issued. Approval, eligibility and stock are rechecked by the server.') }
    finally { setBusy(false) }
  }

  const selectedReturnLine = data?.allocations.find((line) => line.line_id === returnLine)
  const allocatableBalances = data?.balances.filter((item) => Number(item.available) > 0) ?? []
  const activeLines = data?.allocations.filter((line) => ['active', 'partially_returned'].includes(line.line_status)
    && Number(line.quantity) > Number(line.returned_quantity)) ?? []

  return <main className="page-content">
    <PageHeader eyebrow="Authenticated inventory" title="Allocations and returns"
      description="Operational requests use server authorization, current stock checks and an explicit authorized approval. Preview data is never used here." />
    <section className="workflow-panel" aria-label="Create allocation request">
      <h2>Request allocation</h2>
      <form className="workflow-form" onSubmit={(event) => void submitAllocation(event)}>
        <label>Active employee<select required value={employee} onChange={(event) => setEmployee(event.target.value)}><option value="">Choose employee</option>{data?.employees.filter((item) => item.status === 'active').map((item) => <option key={item.id} value={item.id}>{item.employee_number} · {item.first_name} {item.last_name}</option>)}</select></label>
        <label>Inventory type<select value={targetKind} onChange={(event) => { setTargetKind(event.target.value as 'asset' | 'quantity'); setTarget('') }}><option value="asset">Individual asset</option><option value="quantity">Quantity stock</option></select></label>
        {targetKind === 'asset' ? <label>Available asset<select required value={target} onChange={(event) => setTarget(event.target.value)}><option value="">Choose asset</option>{data?.assets.filter((item) => item.lifecycle_status === 'available').map((item: AssetOption) => <option key={item.id} value={item.id}>{item.asset_number ?? item.id} · {item.product_name}</option>)}</select></label>
          : <><label>Available quantity<select required value={target} onChange={(event) => setTarget(event.target.value)}><option value="">Choose product, location and unit</option>{allocatableBalances.map((item) => { const key = `${item.product_id}|${item.location_id}|${item.unit}`; return <option key={key} value={key}>{item.product_name} · {item.location_name} · {item.available} {item.unit}</option> })}</select></label><label>Quantity<input required type="number" min="0.001" step="0.001" value={quantity} onChange={(event) => setQuantity(event.target.value)} /></label></>}
        <button className="button button-primary" disabled={busy || loading || !csrfToken}>Submit request</button>
      </form>
    </section>
    <section className="workflow-panel" aria-label="Record inventory return">
      <h2>Record return</h2>
      <form className="workflow-form" onSubmit={(event) => void submitReturn(event)}>
        <label>Outstanding allocation<select required value={returnLine} onChange={(event) => { setReturnLine(event.target.value); setReturnQuantity('1') }}><option value="">Choose allocation</option>{activeLines.map((line) => <option key={line.line_id} value={line.line_id}>{line.tracked_asset_id ? `Asset ${line.tracked_asset_id}` : `${line.product_id} · ${line.location_id} · ${line.unit}`} · outstanding {Number(line.quantity) - Number(line.returned_quantity)} {line.unit ?? 'asset'}</option>)}</select></label>
        <label>Return quantity<input required type="number" min="0.001" step="0.001" max={selectedReturnLine ? Number(selectedReturnLine.quantity) - Number(selectedReturnLine.returned_quantity) : undefined} value={returnQuantity} onChange={(event) => setReturnQuantity(event.target.value)} /></label>
        <label>Observed condition<select value={condition} onChange={(event) => setCondition(event.target.value)}><option value="good">Good</option>{selectedReturnLine?.tracked_asset_id ? <><option value="repair">Repair</option><option value="damaged">Damaged</option><option value="unknown">Unknown</option></> : <option value="damaged">Damaged (quarantined after verification)</option>}</select></label>
        <button className="button button-primary" disabled={busy || loading || !csrfToken || !returnLine}>Record return</button>
      </form>
      <p className="workflow-help">Damaged quantity returns remain unavailable for allocation until a separately authorized disposition is recorded.</p>
    </section>
    <section className="workflow-panel"><h2>Allocation history and approval queue</h2>{data?.allocations.map((item) => <article className="workflow-list-item" key={item.id}><strong>{item.id}</strong><span>{item.status} · {item.line_status}</span>{item.status === 'pending' && <><button className="button workflow-secondary" disabled={busy} onClick={() => void decide('allocation', item.id, 'approved')}>Approve</button><button className="button workflow-secondary" disabled={busy} onClick={() => void decide('allocation', item.id, 'rejected')}>Reject</button></>}{item.status === 'approved' && <button className="button workflow-secondary" disabled={busy} onClick={() => void issue(item.id)}>Issue approved allocation</button>}</article>)}</section>
    <section className="workflow-panel"><h2>Return verification queue</h2>{data?.returns.map((item: ReturnRow) => <article className="workflow-list-item" key={item.id}><strong>{item.id}</strong><span>{item.quantity} · {item.condition} · {item.status}</span>{item.status === 'pending' && <><button className="button workflow-secondary" disabled={busy} onClick={() => void decide('return', item.id, 'approved')}>Verify</button><button className="button workflow-secondary" disabled={busy} onClick={() => void decide('return', item.id, 'rejected')}>Reject</button></>}</article>)}</section>
    {loading && <p role="status">Loading operational inventory…</p>}{error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}{error && <button className="button workflow-secondary" onClick={() => void refresh()}>Retry</button>}
  </main>
}
