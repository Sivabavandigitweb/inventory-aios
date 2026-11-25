import { useState } from 'react'
import { PageHeader } from '../components/PageHeader'
import { mockEmployeeProvider } from '../employees/mockEmployeeProvider'
import type { WorkflowProviders } from '../workflows/useWorkflowPreview'
import { assetFor, employeeFor, employeeName, productFor, returnFor, useWorkflowPreview } from '../workflows/useWorkflowPreview'
import type { AllocationPreview } from '../workflows/types'
import { WorkflowDialog } from '../workflows/WorkflowDialog'
import '../workflows/workflows.css'

const PAGE_SIZE = 5
function initialSearch() { return new URLSearchParams(window.location.search).get('employee')?.slice(0, 100)
  ?? new URLSearchParams(window.location.search).get('asset')?.slice(0, 100) ?? '' }

export function AllocationsPage(props: WorkflowProviders) {
  const { data, loading, error, retry } = useWorkflowPreview(props)
  const employeeProvider = props.employeeProvider ?? mockEmployeeProvider
  const [search, setSearch] = useState(initialSearch)
  const [department, setDepartment] = useState('')
  const [view, setView] = useState('')
  const [page, setPage] = useState(0)
  const [selected, setSelected] = useState<AllocationPreview | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [employeeSearch, setEmployeeSearch] = useState('')
  const [assetSearch, setAssetSearch] = useState('')
  const [employeeId, setEmployeeId] = useState('')
  const [assetId, setAssetId] = useState('')
  const currentCount = data?.workflow.allocations.filter((item) => !returnFor(data, item.reference)).length ?? 0
  const filtered = (data?.workflow.allocations ?? []).filter((item) => {
    if (!data) return false
    const employee = employeeFor(data, item.employeeId)
    const asset = assetFor(data, item.assetId)
    const product = productFor(data, item.assetId)
    const haystack = [item.reference, employee?.employee_number, employeeName(employee), asset?.identifier, product?.name].join(' ').toLowerCase()
    return haystack.includes(search.trim().toLowerCase())
      && (!department || employee?.department_id === department)
      && (!view || (view === 'current' ? !returnFor(data, item.reference) : Boolean(returnFor(data, item.reference))))
  })
  const visible = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)
  const employeeChoices = data?.employees.filter((employee) =>
    [employee.employee_number, employeeName(employee)].join(' ').toLowerCase().includes(employeeSearch.trim().toLowerCase())) ?? []
  const assetChoices = data?.assets.assets.filter((asset) =>
    [asset.identifier, productFor(data, asset.id)?.name].join(' ').toLowerCase().includes(assetSearch.trim().toLowerCase())) ?? []
  const previewEmployee = data?.employees.find((item) => item.id === employeeId)
  const previewAsset = data?.assets.assets.find((item) => item.id === assetId)

  return <>
    <PageHeader eyebrow="Custody preview" title="Allocations"
      description="Review partial fictional examples of individual-asset custody. Allocation decisions and operational actions are not connected."
      action={<button type="button" className="button button-primary" onClick={() => setCreateOpen(true)}>New Allocation preview</button>} />
    <div className="workflow-banner" role="status"><strong>Fictional preview data</strong> · Partial illustrative examples only. No backend requests or complete inventory coverage.</div>
    <section className="workflow-summary" aria-label="Allocation preview summary">
      <article><span>Illustrative allocations</span><strong>{data?.workflow.allocations.length ?? '—'}</strong></article>
      <article><span>Current custody examples</span><strong>{data ? currentCount : '—'}</strong></article>
      <article><span>Historical returns shown</span><strong>{data?.workflow.returns.length ?? '—'}</strong></article>
      <article><span>Employees referenced</span><strong>{data ? new Set(data.workflow.allocations.map((item) => item.employeeId)).size : '—'}</strong></article>
    </section>
    <section className="workflow-panel" aria-labelledby="allocation-directory-title">
      <div className="workflow-heading"><div><p className="eyebrow">Partial preview</p><h2 id="allocation-directory-title">Allocation directory</h2></div><span className="workflow-tag">Individual assets only</span></div>
      <div className="workflow-filters">
        <label>Search allocations<input type="search" value={search} placeholder="Reference, employee or asset" onChange={(event) => { setSearch(event.target.value); setPage(0) }} /></label>
        <label>Department<select value={department} onChange={(event) => { setDepartment(event.target.value); setPage(0) }}><option value="">All departments</option>{employeeProvider.departments.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
        <label>Preview view<select value={view} onChange={(event) => { setView(event.target.value); setPage(0) }}><option value="">All examples</option><option value="current">Current custody examples</option><option value="history">Historical returns shown</option></select></label>
      </div>
      {loading ? <p className="workflow-message" role="status">Loading allocation preview…</p>
        : error ? <div className="workflow-message" role="alert"><strong>Allocation preview is unavailable.</strong><p>Local preview sources could not load. No live data was requested.</p><button type="button" className="button workflow-secondary" onClick={retry}>Try again</button></div>
          : data && !visible.length ? <p className="workflow-message">No allocation examples found.</p>
            : data ? <>
              <div className="workflow-table-wrap"><table className="workflow-table"><caption className="sr-only">Fictional allocation directory</caption><thead><tr><th>Reference</th><th>Employee</th><th>Department</th><th>Asset</th><th>Product</th><th>Allocation date</th><th>Custody view</th><th>Action</th></tr></thead><tbody>
                {visible.map((item) => { const employee = employeeFor(data, item.employeeId); const asset = assetFor(data, item.assetId); return <tr key={item.reference}>
                  <td data-label="Reference"><strong>{item.reference}</strong></td>
                  <td data-label="Employee">{employee?.employee_number} · {employeeName(employee)}</td>
                  <td data-label="Department">{employeeProvider.departments.find((entry) => entry.id === employee?.department_id)?.name ?? 'Not recorded'}</td>
                  <td data-label="Asset">{asset?.identifier}</td><td data-label="Product">{productFor(data, item.assetId)?.name}</td>
                  <td data-label="Allocation date">{item.allocatedOn}</td>
                  <td data-label="Custody view"><span className={'workflow-badge ' + (returnFor(data, item.reference) ? 'workflow-badge-history' : 'workflow-badge-current')}>{returnFor(data, item.reference) ? 'Historical return shown' : 'Current custody example'}</span></td>
                  <td data-label="Action"><button type="button" className="text-button" aria-label={'View allocation ' + item.reference} onClick={() => setSelected(item)}>View details</button></td>
                </tr> })}</tbody></table></div>
              <div className="workflow-pagination"><span>Showing {page * PAGE_SIZE + 1}–{page * PAGE_SIZE + visible.length} of {filtered.length} · Page {page + 1} of {Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))}</span><div><button type="button" className="button workflow-secondary" disabled={page === 0} onClick={() => setPage((value) => value - 1)}>Previous</button><button type="button" className="button workflow-secondary" disabled={(page + 1) * PAGE_SIZE >= filtered.length} onClick={() => setPage((value) => value + 1)}>Next</button></div></div>
            </> : null}
    </section>
    {selected && data && <WorkflowDialog title={selected.reference} onClose={() => setSelected(null)}>
      <p className="workflow-help">Fictional allocation example. This is not an operational custody record.</p>
      <dl className="workflow-details">
        <div><dt>Employee</dt><dd>{employeeFor(data, selected.employeeId)?.employee_number} · {employeeName(employeeFor(data, selected.employeeId))}</dd></div>
        <div><dt>Asset</dt><dd>{assetFor(data, selected.assetId)?.identifier}</dd></div>
        <div><dt>Product</dt><dd>{productFor(data, selected.assetId)?.name}</dd></div>
        <div><dt>Allocation date</dt><dd>{selected.allocatedOn}</dd></div>
        <div><dt>Assigned by</dt><dd>{selected.assignedBy}</dd></div>
        <div><dt>Asset condition</dt><dd>{selected.conditionNote} · Vocabulary pending</dd></div>
        <div><dt>Custody view</dt><dd>{returnFor(data, selected.reference) ? 'Historical return shown' : 'Current custody example'}</dd></div>
      </dl>
      {returnFor(data, selected.reference) && <a className="workflow-preview-link" href={'/returns?allocation=' + encodeURIComponent(selected.reference)}>View linked fictional return</a>}
      <p className="workflow-help">Approval and eligibility policy remain unresolved. Audit and employee exit clearance are unavailable.</p>
    </WorkflowDialog>}
    {createOpen && <WorkflowDialog title="New Allocation preview" onClose={() => setCreateOpen(false)}>
      <p className="workflow-help">Selections are fictional and do not establish eligibility. Quantity-stock allocation is unavailable. Approval and condition rules remain pending.</p>
      {loading || error || !data ? <p className="workflow-message">Preview sources are unavailable.</p> : <form className="workflow-form" onSubmit={(event) => event.preventDefault()}>
        <label>Search employees<input type="search" value={employeeSearch} placeholder="DEMO code or name" onChange={(event) => setEmployeeSearch(event.target.value)} /></label>
        <label>Select fictional employee<select value={employeeId} onChange={(event) => setEmployeeId(event.target.value)}><option value="">Choose an employee</option>{employeeChoices.map((item) => <option key={item.id} value={item.id}>{item.employee_number} · {employeeName(item)}</option>)}</select></label>
        {previewEmployee && <p className="workflow-selection">Selected: {employeeName(previewEmployee)} · {previewEmployee.employee_number}</p>}
        <label>Search individual assets<input type="search" value={assetSearch} placeholder="DEMO asset ID or product" onChange={(event) => setAssetSearch(event.target.value)} /></label>
        <label>Select fictional asset<select value={assetId} onChange={(event) => setAssetId(event.target.value)}><option value="">Choose an asset</option>{assetChoices.map((item) => <option key={item.id} value={item.id}>{item.identifier} · {productFor(data, item.id)?.name}</option>)}</select></label>
        {previewAsset && <p className="workflow-selection">Selected: {previewAsset.identifier} · {productFor(data, previewAsset.id)?.name} · {previewAsset.status}. Selection is not eligibility approval.</p>}
        <label>Allocation date<input type="date" /></label>
        <label>Assigned by<input type="text" value="Authenticated assigner required" readOnly /></label>
        <label>Asset condition observation<textarea rows={2} placeholder="Condition vocabulary pending approval" /></label>
        <p className="workflow-help">Employee organization, assigner identity, approval and history must be verified by a future authorized backend transaction.</p>
        <button type="submit" className="button button-primary" disabled>Submit allocation (unavailable)</button>
      </form>}
    </WorkflowDialog>}
  </>
}
