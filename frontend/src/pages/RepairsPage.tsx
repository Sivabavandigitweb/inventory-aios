import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { PageHeader } from '../components/PageHeader'
import { WorkflowDialog } from '../workflows/WorkflowDialog'
import type { PreviewAsset } from '../assets/types'
import type { RepairPreviewRecord } from '../repairs/types'
import { useRepairPreview, type RepairPreviewProviders } from '../repairs/useRepairPreview'
import '../workflows/workflows.css'
import '../repairs/repairs.css'

const PAGE_SIZE = 5
function productName(data: NonNullable<ReturnType<typeof useRepairPreview>['data']>, asset: PreviewAsset | undefined) {
  return data.assets.products.find((product) => product.id === asset?.productId)?.name ?? 'Unknown preview product'
}
function RepairDetails({ repair, data, close }: { repair: RepairPreviewRecord; data: NonNullable<ReturnType<typeof useRepairPreview>['data']>; close: () => void }) {
  const asset = data.assets.assets.find((item) => item.id === repair.assetId)
  return <WorkflowDialog title={repair.reference} onClose={close}>
    <p className="workflow-help">Fictional partial example. The group label is for this preview and is not an approved repair state.</p>
    <dl className="workflow-details">
      <div><dt>Asset identifier</dt><dd>{asset?.identifier}</dd></div><div><dt>Product</dt><dd>{productName(data, asset)}</dd></div>
      <div><dt>Reported issue</dt><dd>{repair.reportedIssue}</dd></div><div><dt>Reported date</dt><dd>{repair.reportedDate}</dd></div>
      <div><dt>Reported by</dt><dd>{repair.reportedBy}</dd></div><div><dt>Repair date</dt><dd>{repair.repairDate ?? 'Not recorded in this example'}</dd></div>
      <div><dt>Current asset lifecycle status</dt><dd>{asset?.status ?? 'Unavailable'}</dd></div><div><dt>Repair provider / responsibility</dt><dd>Not recorded</dd></div>
    </dl>
    <div className="repair-details-section"><h3>Assessment and progress</h3><p>Repair classification and progress vocabulary require review.</p></div>
    <div className="repair-details-section"><h3>Outcome and verification</h3><p>No repair outcome or verification is recorded. Asset lifecycle status is not changed by this preview.</p></div>
    <div className="repair-details-section"><h3>Future information</h3><p>Costs, supporting documents, completion evidence, approval and audit history are unavailable.</p></div>
    <Link className="workflow-preview-link" to={'/assets?section=assets'}>Open the asset directory</Link>
  </WorkflowDialog>
}
function NewRepairPreview({ data, close }: { data: NonNullable<ReturnType<typeof useRepairPreview>['data']>; close: () => void }) {
  const [query, setQuery] = useState('')
  const [assetId, setAssetId] = useState('')
  const matches = data.assets.assets.filter((asset) => (asset.identifier + ' ' + productName(data, asset)).toLowerCase().includes(query.toLowerCase()))
  const selected = data.assets.assets.find((asset) => asset.id === assetId)
  return <WorkflowDialog title="New Repair preview" onClose={close}>
    <p className="workflow-help">Preview only. Choosing an asset does not confirm repair eligibility or an approval.</p>
    <div className="repair-form">
      <label>Search assets<input type="search" aria-label="Search assets for repair" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="DEMO identifier or product" /></label>
      <label>Select fictional asset<select aria-label="Select asset for repair" value={assetId} onChange={(event) => setAssetId(event.target.value)}><option value="">Choose an asset</option>{matches.map((asset) => <option key={asset.id} value={asset.id}>{asset.identifier} - {productName(data, asset)}</option>)}</select></label>
      {selected && <p className="workflow-selection">{selected.identifier} - {productName(data, selected)} - Current lifecycle: {selected.status}. Selection is not eligibility approval.</p>}
      <label>Reported issue<input type="text" placeholder="Preview field; no record will be created" /></label>
      <label>Reported date<input type="date" /></label>
      <p className="repair-note">R-09 requires reported date and reporter. Reporter identity comes from future authenticated context; no identity service is connected.</p>
      <p className="repair-note">Repair provider, dates, cost, supporting evidence, approval and status transitions need workflow decisions. No documents or costs can be submitted here.</p>
      <div><button className="button button-primary" type="button" disabled title="Operational repair recording is unavailable">Submit repair (unavailable)</button> <button className="button workflow-secondary" type="button" onClick={close}>Cancel</button></div>
    </div>
  </WorkflowDialog>
}
export function RepairsPage({ assetProvider, employeeProvider, workflowProvider, repairProvider }: RepairPreviewProviders) {
  const preview = useRepairPreview({ assetProvider, employeeProvider, workflowProvider, repairProvider })
  const [query, setQuery] = useState(() => new URLSearchParams(window.location.search).get('asset') ?? '')
  const [group, setGroup] = useState('')
  const [page, setPage] = useState(0)
  const [selected, setSelected] = useState<RepairPreviewRecord | null>(null)
  const [newOpen, setNewOpen] = useState(false)
  const data = preview.data
  const visible = useMemo(() => {
    if (!data) return []
    return data.repairs.repairs.filter((repair) => {
      const asset = data.assets.assets.find((item) => item.id === repair.assetId)
      const product = data.assets.products.find((item) => item.id === asset?.productId)
      const search = [repair.reference, repair.reportedIssue, repair.reportedBy, asset?.identifier, product?.name].join(' ').toLowerCase()
      return search.includes(query.toLowerCase()) && (!group || repair.exampleGroup === group)
    })
  }, [data, query, group])
  const pages = Math.max(1, Math.ceil(visible.length / PAGE_SIZE))
  const rows = visible.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)
  const openCount = data?.repairs.repairs.filter((repair) => repair.exampleGroup === 'Open example').length ?? 0
  const historicalCount = data?.repairs.repairs.filter((repair) => repair.exampleGroup === 'Historical example').length ?? 0
  return <>
    <PageHeader eyebrow="Asset lifecycle" title="Repairs" description="Review fictional repair examples linked to the asset preview. Operational repair records are not connected." />
    <div className="workflow-banner" role="status"><strong>Fictional, partial preview data</strong> - DEMO records only; not a complete history or live service.</div>
    {preview.loading ? <div className="workflow-message" role="status">Loading repair preview...</div>
      : preview.error ? <div className="workflow-message" role="alert"><strong>Repair preview is unavailable.</strong><p>The local providers could not load; no live data was requested.</p><button type="button" className="button workflow-secondary" onClick={preview.retry}>Try again</button></div>
        : data ? <>
          <section className="repair-summary" aria-label="Repair preview summary">
            <article><span>Example repair records</span><strong>{data.repairs.repairs.length}</strong></article>
            <article><span>Open examples</span><strong>{openCount}</strong></article>
            <article><span>Historical examples</span><strong>{historicalCount}</strong></article>
          </section>
          <section className="workflow-panel" aria-labelledby="repair-directory-title">
            <div className="workflow-heading"><div><p className="eyebrow">R-09 preview</p><h2 id="repair-directory-title">Repair directory</h2></div><button type="button" className="button button-primary" onClick={() => setNewOpen(true)}>New Repair preview</button></div>
            <p className="repair-note">-Open example- and -Historical example- are presentation groupings only, not approved repair states or outcomes. R-09 confirms reported date/by, repair date, repair cost, service provider and current status fields.</p>
            <div className="repair-toolbar">
              <label>Search repairs<input type="search" aria-label="Search repairs" value={query} onChange={(event) => { setQuery(event.target.value); setPage(0) }} placeholder="Reference, asset, product or issue" /></label>
              <label>Preview grouping<select aria-label="Preview grouping" value={group} onChange={(event) => { setGroup(event.target.value); setPage(0) }}><option value="">All examples</option><option>Open example</option><option>Historical example</option></select></label>
            </div>
            {!rows.length ? <p className="workflow-message">{data.repairs.repairs.length ? 'No repair examples match these filters.' : 'No repair examples are available.'}</p> : <div className="workflow-table-wrap"><table className="workflow-table"><caption className="sr-only">Fictional repair directory</caption><thead><tr><th>Repair reference</th><th>Asset / product</th><th>Reported issue</th><th>Reported date / by</th><th>Preview grouping</th><th>Action</th></tr></thead><tbody>{rows.map((repair) => { const asset = data.assets.assets.find((item) => item.id === repair.assetId); return <tr key={repair.reference}><td data-label="Repair reference"><strong>{repair.reference}</strong></td><td data-label="Asset / product">{asset?.identifier}<br />{productName(data, asset)}</td><td data-label="Reported issue">{repair.reportedIssue}</td><td data-label="Reported date / by">{repair.reportedDate}<br />{repair.reportedBy}</td><td data-label="Preview grouping"><span className={'repair-state' + (repair.exampleGroup === 'Historical example' ? ' repair-state-history' : '')}>{repair.exampleGroup}</span></td><td data-label="Action"><button className="text-button" type="button" aria-label={'View repair ' + repair.reference} onClick={() => setSelected(repair)}>Details</button></td></tr> })}</tbody></table></div>}
            <div className="workflow-pagination"><span>Showing {visible.length ? page * PAGE_SIZE + 1 : 0}-{Math.min((page + 1) * PAGE_SIZE, visible.length)} of {visible.length} - Page {page + 1} of {pages}</span><div><button className="button workflow-secondary" type="button" disabled={page === 0} onClick={() => setPage((value) => value - 1)}>Previous</button><button className="button workflow-secondary" type="button" disabled={page + 1 >= pages} onClick={() => setPage((value) => value + 1)}>Next</button></div></div>
          </section>
          <section className="workflow-panel" style={{ marginTop: 16 }} aria-labelledby="maintenance-title"><p className="eyebrow">Future capability</p><h2 id="maintenance-title">Preventive maintenance</h2><p className="repair-note">No preventive maintenance schedule or service interval was found in the reviewed R-09 requirement. Scheduled servicing is a proposed enhancement requiring approval; no schedule or reminders are shown.</p></section>
        </> : null}
    {selected && data && <RepairDetails repair={selected} data={data} close={() => setSelected(null)} />}
    {newOpen && data && <NewRepairPreview data={data} close={() => setNewOpen(false)} />}
  </>
}
