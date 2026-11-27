import { useEffect, useState } from 'react'
import { PageHeader } from '../components/PageHeader'
import { mockAssetProvider } from '../assets/mockAssetProvider'
import type { AssetPreviewData, AssetPreviewProvider, PreviewAsset, PreviewProduct } from '../assets/types'
import type { InventoryWriteProvider } from '../assets/apiInventoryWriteProvider'
import { InventoryWritePanel } from '../assets/InventoryWritePanel'
import '../assets/assets.css'

type Section = 'assets' | 'quantity' | 'products' | 'receiving'
const PAGE_SIZE = 5
const sections: { id: Section; label: string }[] = [
  { id: 'assets', label: 'Individual assets' },
  { id: 'quantity', label: 'Quantity inventory' },
  { id: 'products', label: 'Product catalog' },
  { id: 'receiving', label: 'Receiving' },
]
const statuses = ['Available', 'Allocated', 'Repair', 'Damaged', 'Disposed']

function StatusBadge({ status }: { status: PreviewAsset['status'] }) {
  return <span className={'asset-status asset-status-' + status.toLowerCase()}>{status}</span>
}

function conditionLabel(value: string): string {
  return value === 'Preview description; condition vocabulary pending' ? 'Not specified' : value
}

function initialSection(): Section {
  const value = new URLSearchParams(window.location.search).get('section')
  return sections.find((item) => item.id === value)?.id ?? 'assets'
}
function productFor(data: AssetPreviewData, id: string): PreviewProduct | undefined {
  return data.products.find((product) => product.id === id)
}

function AssetDetails({ asset, product, onClose }: {
  asset: PreviewAsset; product?: PreviewProduct; onClose: () => void
}) {
  useEffect(() => {
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const dialog = document.querySelector<HTMLElement>('.asset-dialog')
    dialog?.querySelector<HTMLElement>('button')?.focus()
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
      if (event.key !== 'Tab' || !dialog) return
      const controls = [...dialog.querySelectorAll<HTMLElement>('button:not([disabled]), a[href]')]
      if (!controls.length) return
      if (event.shiftKey && document.activeElement === controls[0]) {
        event.preventDefault()
        controls[controls.length - 1].focus()
      } else if (!event.shiftKey && document.activeElement === controls[controls.length - 1]) {
        event.preventDefault()
        controls[0].focus()
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => { document.removeEventListener('keydown', onKeyDown); previous?.focus() }
  }, [onClose])
  return <div className="asset-backdrop">
    <div className="asset-dialog" role="dialog" aria-modal="true" aria-labelledby="asset-detail-title">
      <div className="asset-heading">
        <div><p className="eyebrow">Asset record</p><h2 id="asset-detail-title">{asset.identifier}</h2></div>
        <button type="button" className="asset-close" onClick={onClose} aria-label="Close panel">×</button>
      </div>
      <dl className="asset-detail-list">
        <div><dt>Product</dt><dd>{product?.name ?? 'Unknown preview product'}</dd></div>
        <div><dt>Category</dt><dd>{product?.category ?? 'Not recorded'}</dd></div>
        <div><dt>Brand / model</dt><dd>{[product?.brand, product?.model].filter(Boolean).join(' / ') || 'Not recorded'}</dd></div>
        <div><dt>Location</dt><dd>{asset.location}</dd></div>
        <div><dt>Condition</dt><dd>{conditionLabel(asset.condition)}</dd></div>
        <div><dt>Lifecycle status</dt><dd><StatusBadge status={asset.status} /></dd></div>
      </dl>
      <a className="asset-preview-link" href={'/allocations?asset=' + encodeURIComponent(asset.identifier)}>View fictional allocation examples</a>
      <a className="asset-preview-link" href={'/repairs?asset=' + encodeURIComponent(asset.identifier)}>View fictional repair examples</a>
      <h3>Future history</h3>
      <p>Allocation, repair, return, transfer and audit history are unavailable. No operational history is connected.</p>
    </div>
  </div>
}

export function AssetsPage({ provider = mockAssetProvider, writeProvider, csrfToken = '' }: {
  provider?: AssetPreviewProvider; writeProvider?: InventoryWriteProvider; csrfToken?: string
}) {
  const previewMode = provider.mode !== 'authenticated-api'
  const [data, setData] = useState<AssetPreviewData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [retry, setRetry] = useState(0)
  const [section, setSection] = useState<Section>(initialSection)
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState('')
  const [status, setStatus] = useState('')
  const [location, setLocation] = useState('')
  const [page, setPage] = useState(0)
  const [productQuery, setProductQuery] = useState('')
  const [selected, setSelected] = useState<PreviewAsset | null>(null)
  function refreshAfterConfirmedWrite() { setLoading(true); setRetry((value) => value + 1) }

  useEffect(() => {
    let current = true
    provider.load().then((next) => {
      if (current) { setData(next); setError(false); setLoading(false) }
    }).catch(() => {
      if (current) { setData(null); setError(true); setLoading(false) }
    })
    return () => { current = false }
  }, [provider, retry])

  const categories = [...new Set(data?.products.map((product) => product.category) ?? [])].sort()
  const locations = [...new Set([
    ...(data?.assets.map((asset) => asset.location) ?? []),
    ...(data?.lots.map((lot) => lot.location) ?? []),
  ])].sort()
  const filtered = (data?.assets ?? []).filter((asset) => {
    const product = data && productFor(data, asset.productId)
    const haystack = [asset.identifier, product?.name, product?.category, product?.brand, product?.model, asset.location].join(' ').toLowerCase()
    return haystack.includes(query.trim().toLowerCase())
      && (!category || product?.category === category)
      && (!status || asset.status === status)
      && (!location || asset.location === location)
  })
  const visible = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)
  const pages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const productMatches = (data?.products ?? []).filter((product) =>
    [product.name, product.category, product.sku, product.brand, product.model, product.specifications]
      .join(' ').toLowerCase().includes(productQuery.trim().toLowerCase()))
  const quantityUnits = [...new Set(data?.lots.map((lot) => lot.unit) ?? [])]
  const totalPhysical = quantityUnits.length === 1 ? data?.lots.reduce((sum, lot) => sum + lot.physical, 0) ?? 0 : null
  const totalAvailable = quantityUnits.length === 1 ? data?.lots.reduce((sum, lot) => sum + lot.physical - lot.reserved, 0) ?? 0 : null

  return <>
    <PageHeader eyebrow="Inventory" title="Assets" description={previewMode ? 'Explore fictional assets and inventory in a local preview.' : 'Search inventory records from the protected Inventory AIOS API.'} />
    <div className="asset-preview-banner" role="status"><strong>{previewMode ? 'Fictional preview data' : 'Protected operational API'}</strong> · {previewMode ? 'DEMO records only. No backend requests or real company asset records.' : 'API failures are shown; preview data is never substituted.'}</div>
    <section className="asset-summary" aria-label="Asset summary">
      <article><span>Individual assets</span><strong>{data?.assets.length ?? '—'}</strong></article>
      <article><span>Available assets</span><strong>{data?.assets.filter((asset) => asset.status === 'Available').length ?? '—'}</strong></article>
      <article><span>Quantity stock (physical)</span><strong>{data ? totalPhysical ?? 'View by unit' : '—'}</strong></article>
      <article><span>Quantity stock (available)</span><strong>{data ? totalAvailable ?? 'View by unit' : '—'}</strong></article>
    </section>
    <p className="asset-summary-note">{previewMode
      ? 'Quantity totals are fictional whole-item counts only.'
      : 'Quantity totals are combined only when all returned balances use the same unit; review the unit column for individual balances.'}</p>
    <div className="asset-tabs" role="tablist" aria-label="Asset sections">
      {sections.map((item) => <button key={item.id} id={'tab-' + item.id} role="tab" type="button"
        aria-selected={section === item.id} aria-controls="asset-section-panel"
        onKeyDown={(event) => {
          if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
          event.preventDefault()
          const index = sections.findIndex((entry) => entry.id === item.id)
          const next = event.key === 'Home' ? 0 : event.key === 'End' ? sections.length - 1
            : (index + (event.key === 'ArrowRight' ? 1 : -1) + sections.length) % sections.length
          setSection(sections[next].id)
          event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>('[role="tab"]')[next]?.focus()
        }}
        onClick={() => { setSection(item.id); setSelected(null) }}>{item.label}</button>)}
    </div>
    <section className="asset-panel" id="asset-section-panel" role="tabpanel" aria-labelledby={'tab-' + section}>
      {loading ? <p role="status">Loading asset preview…</p> :
        error ? <div role="alert"><strong>Asset preview is unavailable.</strong><p>The local provider could not load. No live data was requested.</p><button className="button asset-secondary" type="button" onClick={() => { setLoading(true); setRetry((value) => value + 1) }}>Try again</button></div> :
          data && section === 'assets' ? <>
            <div className="asset-heading"><div><p className="eyebrow">Directory</p><h2>Individual assets</h2></div><span className="asset-tag">Proposed preview fields</span></div>
            <p className="asset-condition-note">Condition vocabulary is pending approval; neutral preview labels do not imply an assessment.</p>
            <div className="asset-filters">
              <label>Search assets<input type="search" value={query} placeholder="DEMO ID, product, brand or location" onChange={(event) => { setQuery(event.target.value); setPage(0) }} /></label>
              <label>Category<select value={category} onChange={(event) => { setCategory(event.target.value); setPage(0) }}><option value="">All categories</option>{categories.map((item) => <option key={item}>{item}</option>)}</select></label>
              <label>Lifecycle status<select value={status} onChange={(event) => { setStatus(event.target.value); setPage(0) }}><option value="">All statuses</option>{statuses.map((item) => <option key={item}>{item}</option>)}</select></label>
              <label>Location<select value={location} onChange={(event) => { setLocation(event.target.value); setPage(0) }}><option value="">All locations</option>{locations.map((item) => <option key={item}>{item}</option>)}</select></label>
            </div>
            {!visible.length ? <p className="asset-empty">No individual assets found. Try another search or filter.</p> : <>
              <div className="asset-table-wrap"><table className="asset-table"><caption className="sr-only">{previewMode ? 'Fictional individual asset directory' : 'Individual asset directory'}</caption><thead><tr><th>Asset ID</th><th>Product</th><th>Category</th><th>Brand / model</th><th>Location</th><th>Condition</th><th>Status</th><th>Action</th></tr></thead><tbody>
                {visible.map((asset) => { const product = productFor(data, asset.productId); return <tr key={asset.id}>
                  <td data-label="Asset ID"><strong>{asset.identifier}</strong></td><td data-label="Product">{product?.name}</td><td data-label="Category">{product?.category}</td>
                  <td data-label="Brand / model">{[product?.brand, product?.model].filter(Boolean).join(' / ') || 'Not recorded'}</td>
                  <td data-label="Location">{asset.location}</td><td data-label="Condition">{conditionLabel(asset.condition)}</td><td data-label="Status"><StatusBadge status={asset.status} /></td>
                  <td data-label="Action"><button className="text-button" type="button" aria-label={'View details for ' + asset.identifier} onClick={() => setSelected(asset)}>View details</button></td>
                </tr> })}</tbody></table></div>
              <div className="asset-pagination"><span>Showing {page * PAGE_SIZE + 1}–{page * PAGE_SIZE + visible.length} of {filtered.length} · Page {page + 1} of {pages}</span><div><button className="button asset-secondary" type="button" disabled={page === 0} onClick={() => setPage((value) => value - 1)}>Previous</button><button className="button asset-secondary" type="button" disabled={page + 1 >= pages} onClick={() => setPage((value) => value + 1)}>Next</button></div></div>
            </>}
          </> : data && section === 'quantity' ? <>
            <div className="asset-heading"><div><p className="eyebrow">Separate stock view</p><h2>Quantity inventory</h2></div><span className="asset-tag">Illustrative whole counts; units pending</span></div>
            <p className="asset-note">{previewMode ? 'These quantities are fictional and remain separate from the individual asset count.' : 'Quantity balances remain separate from individually tracked assets and are grouped by unit.'}</p>
            {!data.lots.length ? <p className="asset-empty">No quantity inventory is recorded.</p> : <div className="asset-table-wrap"><table className="asset-table"><caption className="sr-only">{previewMode ? 'Fictional quantity inventory' : 'Quantity inventory by compatible unit'}</caption><thead><tr><th>Product</th><th>Category</th><th>Location</th><th>Lot reference</th><th>Unit</th><th>Physical</th><th>Reserved</th><th>Available</th></tr></thead><tbody>{data.lots.map((lot) => { const product = productFor(data, lot.productId); return <tr key={lot.id}><td data-label="Product">{product?.name}</td><td data-label="Category">{product?.category}</td><td data-label="Location">{lot.location}</td><td data-label="Lot reference">{lot.reference}</td><td data-label="Unit">{lot.unit}</td><td data-label="Physical">{lot.physical}</td><td data-label="Reserved">{lot.reserved}</td><td data-label="Available">{lot.physical - lot.reserved}</td></tr> })}</tbody></table></div>}
          </> : data && section === 'products' ? <>
            <div className="asset-heading"><div><p className="eyebrow">Product catalog</p><h2>Product catalog</h2></div>{writeProvider ? <a className="asset-preview-link" href="#inventory-write-heading">Open product form</a> : <button className="button asset-secondary" type="button" disabled title="Product creation is unavailable">Add product (unavailable)</button>}</div>
            <label className="asset-product-search">Search products<input type="search" value={productQuery} placeholder="Name, category, SKU, brand or model" onChange={(event) => setProductQuery(event.target.value)} /></label>
            {!productMatches.length ? <p className="asset-empty">No products found.</p> : <div className="asset-table-wrap"><table className="asset-table"><caption className="sr-only">{previewMode ? 'Fictional product catalog' : 'Protected product catalog'}</caption><thead><tr><th>Product</th><th>Category</th><th>SKU</th><th>Brand</th><th>Model</th><th>Specifications</th><th>Active</th></tr></thead><tbody>{productMatches.map((product) => <tr key={product.id}><td data-label="Product">{product.name}</td><td data-label="Category">{product.category}</td><td data-label="SKU">{product.sku ?? 'Not recorded'}</td><td data-label="Brand">{product.brand ?? 'Not recorded'}</td><td data-label="Model">{product.model ?? 'Not recorded'}</td><td data-label="Specifications">{product.specifications}</td><td data-label="Active">{product.active ? 'Yes' : 'No'}</td></tr>)}</tbody></table></div>}
          </> : data ? <>
            <div className="asset-heading"><div><p className="eyebrow">Receiving preview</p><h2>Receiving</h2></div><span className="asset-tag">No transactions available</span></div>
            <p className="asset-note">Confirmed arrival fields: received date, received by, quantity, location and technical specifications. Supporting documents are optional.</p>
            <div className="asset-receiving-grid">
              <div><h3>{previewMode ? 'Illustrative arrivals' : 'Receiving history'}</h3>{data.receipts.length ? <ul className="asset-receipts">{data.receipts.map((receipt) => <li key={receipt.id}><strong>{receipt.receivedDate}</strong><span>{receipt.receivedBy} · {receipt.quantity === null ? 'Line details not included' : `${receipt.quantity} items`} · {receipt.location}</span><small>{receipt.specifications}</small></li>)}</ul> : <p className="asset-empty">No receiving records are available.</p>}</div>
              <div className="asset-receiving-card"><h3>New arrival</h3>{writeProvider ? <p>Use the protected receiving form below. A receipt does not add stock until registration is approved and posted.</p> : <p>A receiving form and submission are unavailable.</p>}<dl><div><dt>Received date</dt><dd>Required by R-03</dd></div><div><dt>Receiver</dt><dd>{previewMode ? 'Identity policy pending' : 'Authenticated actor'}</dd></div><div><dt>Quantity / unit</dt><dd>{previewMode ? 'Unit and precision pending' : 'Separate compatible units'}</dd></div><div><dt>Location</dt><dd>Required by R-03</dd></div><div><dt>Specifications</dt><dd>Required by R-03</dd></div><div><dt>Documents</dt><dd>Optional</dd></div></dl>{writeProvider ? <a className="asset-preview-link" href="#inventory-write-heading">Open receiving form</a> : <button className="button button-primary" type="button" disabled>Record receipt (unavailable)</button>}</div>
            </div>
            <p className="asset-note">Purchase fields, partial deliveries, discrepancy handling, approval timing and asset numbering require decisions. No asset ID is generated here.</p>
          </> : null}
    </section>
    {writeProvider && !previewMode && <InventoryWritePanel provider={writeProvider} csrfToken={csrfToken} onConfirmed={refreshAfterConfirmedWrite} />}
    {selected && data && <AssetDetails asset={selected} product={productFor(data, selected.productId)} onClose={() => setSelected(null)} />}
  </>
}
