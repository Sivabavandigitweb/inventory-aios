import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import type { InventoryWriteProvider, CategoryOption, LocationOption, ProductOption, RegistrationApproval, RegistrationCandidate, RegistrationFinalization } from './apiInventoryWriteProvider'
import './assets.css'

type Props = { provider: InventoryWriteProvider; csrfToken: string; onConfirmed: () => void }

export function InventoryWritePanel({ provider, csrfToken, onConfirmed }: Props) {
  const [categories, setCategories] = useState<CategoryOption[]>([])
  const [locations, setLocations] = useState<LocationOption[]>([])
  const [products, setProducts] = useState<ProductOption[]>([])
  const [assets, setAssets] = useState<RegistrationCandidate[]>([])
  const [quantities, setQuantities] = useState<RegistrationCandidate[]>([])
  const [approvals, setApprovals] = useState<RegistrationApproval[]>([])
  const [finalizations, setFinalizations] = useState<RegistrationFinalization[]>([])
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const reload = useCallback(async () => {
    setLoading(true); setError('')
    try {
      const [c, l, p, a, q, approvalsResult, finalizationResult] = await Promise.all([
        provider.loadCategories(), provider.loadLocations(), provider.loadProducts(),
        provider.loadCandidates('individual'), provider.loadCandidates('quantity'),
        provider.loadApprovals(), provider.loadFinalizations(),
      ])
      setCategories(c); setLocations(l); setProducts(p); setAssets(a); setQuantities(q)
      setApprovals(approvalsResult); setFinalizations(finalizationResult)
    } catch { setError('Inventory operations are unavailable. No preview data was substituted.') }
    finally { setLoading(false) }
  }, [provider])
  useEffect(() => { void reload() }, [reload])

  const activeProducts = useMemo(() => products.filter((product) => product.active), [products])
  const trackingByCategory = useMemo(() => new Map(categories.map((item) => [item.id, item.tracking_mode])), [categories])
  async function submit(event: FormEvent<HTMLFormElement>, action: (data: FormData) => Promise<string>) {
    event.preventDefault()
    const form = event.currentTarget
    setBusy(true); setError(''); setNotice('')
    try {
      const message = await action(new FormData(form))
      form.reset(); setNotice(message); await reload(); onConfirmed()
    } catch { setError('The request was not confirmed. Refresh current records before retrying.') }
    finally { setBusy(false) }
  }
  async function decide(item: RegistrationApproval, decision: 'approved' | 'rejected') {
    setBusy(true); setError(''); setNotice('')
    try { await provider.decideApproval(item.id, decision, csrfToken); setNotice(`Approval ${decision} was recorded.`); await reload(); onConfirmed() }
    catch { setError('The decision was not confirmed. Refresh approvals before retrying.') }
    finally { setBusy(false) }
  }
  async function finalize(item: RegistrationFinalization) {
    setBusy(true); setError(''); setNotice('')
    try { await provider.finalizeRegistration(item.request_id, item.tracking_mode, csrfToken); setNotice('Approved registration was posted successfully.'); await reload(); onConfirmed() }
    catch { setError('Registration was not posted. Stock remains unchanged; refresh and retry if still approved.') }
    finally { setBusy(false) }
  }
  const candidateLabel = (item: RegistrationCandidate) => `${item.product_name} · ${item.location_name} · ${item.remaining_quantity} of ${item.quantity} remaining`

  return <section className="inventory-write-panel" aria-labelledby="inventory-write-heading">
    <div className="asset-heading"><div><p className="eyebrow">Authenticated operations</p><h2 id="inventory-write-heading">Catalog, receiving and registration</h2></div><button className="button asset-secondary" type="button" disabled={loading || busy} onClick={() => void reload()}>Refresh</button></div>
    <p className="asset-note">Writes require server authorization and approval. Receipt entry alone does not make stock available. Registration is posted only after approval and a confirmed transaction.</p>
    {loading && <p role="status">Loading operational options…</p>}
    {error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    {!loading && <div className="inventory-write-grid">
      <form onSubmit={(e) => submit(e, async (d) => {
        const category_id = String(d.get('category_id') ?? '')
        if (!category_id) throw new Error()
        const result = await provider.createProduct({ category_id, name: String(d.get('name') ?? ''), sku: String(d.get('sku') ?? '') || undefined, brand: String(d.get('brand') ?? '') || undefined, model: String(d.get('model') ?? '') || undefined }, csrfToken)
        return `Product request confirmed: ${result.status}.`
      })}>
        <h3>New product</h3>
        <label>Category<select name="category_id" required defaultValue=""><option value="" disabled>Select category</option>{categories.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></label>
        <label>Product name<input name="name" required maxLength={200} /></label><label>SKU<input name="sku" maxLength={80} /></label>
        <label>Brand<input name="brand" maxLength={150} /></label><label>Model<input name="model" maxLength={150} /></label>
        <button className="button button-primary" disabled={busy || !csrfToken || !categories.length}>Submit product</button>
      </form>
      <form onSubmit={(e) => submit(e, async (d) => {
        const product_id = String(d.get('product_id') ?? '')
        const product = activeProducts.find((x) => x.id === product_id)
        const tracking_mode = product && trackingByCategory.get(product.category_id)
        if (!product || !tracking_mode) throw new Error()
        const result = await provider.createReceipt({ received_at: new Date(String(d.get('received_at') ?? '')).toISOString(), location_id: String(d.get('location_id') ?? ''), lines: [{ product_id, quantity: String(d.get('quantity') ?? ''), unit: String(d.get('unit') ?? ''), tracking_mode }] }, csrfToken)
        return `Receiving record confirmed: ${result.status}. Stock is not yet available.`
      })}>
        <h3>Record receiving</h3><label>Received at<input name="received_at" type="datetime-local" required /></label>
        <label>Location<select name="location_id" required defaultValue=""><option value="" disabled>Select location</option>{locations.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></label>
        <label>Product<select name="product_id" required defaultValue=""><option value="" disabled>Select product</option>{activeProducts.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></label>
        <label>Quantity<input name="quantity" type="number" min="0.001" step="0.001" required /></label><label>Unit<input name="unit" maxLength={30} required /></label>
        <button className="button button-primary" disabled={busy || !csrfToken || !activeProducts.length || !locations.length}>Submit receipt</button>
      </form>
      <form onSubmit={(e) => submit(e, async (d) => {
        const receipt_line_id = String(d.get('receipt_line_id') ?? '')
        if (!assets.some((x) => x.id === receipt_line_id)) throw new Error()
        const result = await provider.submitAssetRegistration({ receipt_line_id, asset_number: String(d.get('asset_number') ?? '') || undefined, serial_number: String(d.get('serial_number') ?? '') || undefined }, csrfToken)
        return `Individual registration submitted: ${result.status}. Approval and posting are still required.`
      })}>
        <h3>Register individual assets</h3><label>Approved receipt line<select name="receipt_line_id" required defaultValue=""><option value="" disabled>Select receipt line</option>{assets.map((x) => <option key={x.id} value={x.id}>{candidateLabel(x)}</option>)}</select></label>
        <label>Asset number, if assigned<input name="asset_number" maxLength={100} /></label><label>Serial number, if recorded<input name="serial_number" maxLength={150} /></label>
        <button className="button button-primary" disabled={busy || !csrfToken || !assets.length}>Submit registration</button>
      </form>
      <form onSubmit={(e) => submit(e, async (d) => {
        const receipt_line_id = String(d.get('receipt_line_id') ?? '')
        const candidate = quantities.find((x) => x.id === receipt_line_id)
        if (!candidate) throw new Error()
        const result = await provider.submitQuantityRegistration({ receipt_line_id, quantity: String(d.get('quantity') ?? ''), unit: candidate.unit }, csrfToken)
        return `Quantity registration submitted: ${result.status}. Approval and posting are still required.`
      })}>
        <h3>Register quantity stock</h3><label>Approved receipt line<select name="receipt_line_id" required defaultValue=""><option value="" disabled>Select receipt line</option>{quantities.map((x) => <option key={x.id} value={x.id}>{candidateLabel(x)} · {x.unit}</option>)}</select></label>
        <label>Quantity to register<input name="quantity" type="number" min="0.001" step="0.001" required /></label>
        <button className="button button-primary" disabled={busy || !csrfToken || !quantities.length}>Submit registration</button>
      </form>
      <section aria-labelledby="registration-approvals-heading"><h3 id="registration-approvals-heading">Pending registration approvals</h3>
        {!approvals.length ? <p className="asset-note">No pending approvals are available.</p> : approvals.map((x) => <article className="inventory-approval-item" key={x.id}><p><strong>{x.entity_type.replaceAll('_', ' ')}</strong><br /><code>{x.entity_id}</code></p><div><button type="button" className="button asset-secondary" disabled={busy || !csrfToken} onClick={() => void decide(x, 'approved')}>Approve</button><button type="button" className="button asset-secondary" disabled={busy || !csrfToken} onClick={() => void decide(x, 'rejected')}>Reject</button></div></article>)}
      </section>
      <section aria-labelledby="registration-finalize-heading"><h3 id="registration-finalize-heading">Approved registrations awaiting posting</h3>
        {!finalizations.length ? <p className="asset-note">No approved registrations are awaiting posting.</p> : finalizations.map((x) => <article className="inventory-approval-item" key={x.request_id}><p><strong>{x.product_name}</strong><br />{x.quantity} {x.unit} · {x.tracking_mode}</p><button type="button" className="button button-primary" disabled={busy || !csrfToken} onClick={() => void finalize(x)}>Post approved stock</button></article>)}
      </section>
    </div>}
  </section>
}
