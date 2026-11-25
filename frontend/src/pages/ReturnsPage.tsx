import { useState } from 'react'
import { PageHeader } from '../components/PageHeader'
import { mockEmployeeProvider } from '../employees/mockEmployeeProvider'
import type { WorkflowProviders } from '../workflows/useWorkflowPreview'
import { allocationFor, assetFor, employeeFor, employeeName, productFor, returnFor, useWorkflowPreview } from '../workflows/useWorkflowPreview'
import type { ReturnPreview } from '../workflows/types'
import { WorkflowDialog } from '../workflows/WorkflowDialog'
import '../workflows/workflows.css'

const PAGE_SIZE = 5
function initialSearch() { return new URLSearchParams(window.location.search).get('allocation')?.slice(0, 100) ?? '' }

export function ReturnsPage(props: WorkflowProviders) {
  const { data, loading, error, retry } = useWorkflowPreview(props)
  const employeeProvider = props.employeeProvider ?? mockEmployeeProvider
  const [search, setSearch] = useState(initialSearch)
  const [department, setDepartment] = useState('')
  const [location, setLocation] = useState('')
  const [page, setPage] = useState(0)
  const [selected, setSelected] = useState<ReturnPreview | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [allocationSearch, setAllocationSearch] = useState('')
  const [allocationRef, setAllocationRef] = useState('')
  const locations = [...new Set(data?.workflow.returns.map((item) => item.receivingLocation) ?? [])].sort()
  const filtered = (data?.workflow.returns ?? []).filter((item) => {
    if (!data) return false
    const allocation = allocationFor(data, item.allocationReference)
    const employee = allocation && employeeFor(data, allocation.employeeId)
    const asset = allocation && assetFor(data, allocation.assetId)
    const product = allocation && productFor(data, allocation.assetId)
    const haystack = [item.reference, item.allocationReference, employee?.employee_number, employeeName(employee), asset?.identifier, product?.name].join(' ').toLowerCase()
    return haystack.includes(search.trim().toLowerCase())
      && (!department || employee?.department_id === department)
      && (!location || item.receivingLocation === location)
  })
  const visible = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)
  const current = data?.workflow.allocations.filter((item) => !returnFor(data, item.reference)) ?? []
  const allocationChoices = current.filter((item) => {
    if (!data) return false
    const employee = employeeFor(data, item.employeeId)
    const asset = assetFor(data, item.assetId)
    return [item.reference, employee?.employee_number, employeeName(employee), asset?.identifier].join(' ').toLowerCase().includes(allocationSearch.trim().toLowerCase())
  })
  const selectedAllocation = data && allocationFor(data, allocationRef)

  return <>
    <PageHeader eyebrow="Custody preview" title="Returns"
      description="Review partial fictional examples of individual-asset returns. Verification and exit clearance are not connected."
      action={<button type="button" className="button button-primary" onClick={() => setCreateOpen(true)}>Record Return preview</button>} />
    <div className="workflow-banner" role="status"><strong>Fictional preview data</strong> · Partial illustrative examples only. No backend requests or complete return history.</div>
    <section className="workflow-summary" aria-label="Return preview summary">
      <article><span>Illustrative returns</span><strong>{data?.workflow.returns.length ?? '—'}</strong></article>
      <article><span>Related allocations</span><strong>{data ? new Set(data.workflow.returns.map((item) => item.allocationReference)).size : '—'}</strong></article>
      <article><span>Employees referenced</span><strong>{data ? new Set(data.workflow.returns.map((item) => allocationFor(data, item.allocationReference)?.employeeId)).size : '—'}</strong></article>
      <article><span>Receiving locations</span><strong>{data ? locations.length : '—'}</strong></article>
    </section>
    <section className="workflow-panel" aria-labelledby="return-directory-title">
      <div className="workflow-heading"><div><p className="eyebrow">Partial preview</p><h2 id="return-directory-title">Return directory</h2></div><span className="workflow-tag">No deadline data</span></div>
      <div className="workflow-filters">
        <label>Search returns<input type="search" value={search} placeholder="Return, allocation, employee or asset" onChange={(event) => { setSearch(event.target.value); setPage(0) }} /></label>
        <label>Department<select value={department} onChange={(event) => { setDepartment(event.target.value); setPage(0) }}><option value="">All departments</option>{employeeProvider.departments.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
        <label>Receiving location<select value={location} onChange={(event) => { setLocation(event.target.value); setPage(0) }}><option value="">All locations</option>{locations.map((item) => <option key={item}>{item}</option>)}</select></label>
      </div>
      {loading ? <p className="workflow-message" role="status">Loading return preview…</p>
        : error ? <div className="workflow-message" role="alert"><strong>Return preview is unavailable.</strong><p>Local preview sources could not load. No live data was requested.</p><button type="button" className="button workflow-secondary" onClick={retry}>Try again</button></div>
          : data && !visible.length ? <p className="workflow-message">No return examples found.</p>
            : data ? <>
              <div className="workflow-table-wrap"><table className="workflow-table"><caption className="sr-only">Fictional return directory</caption><thead><tr><th>Return</th><th>Employee</th><th>Asset</th><th>Product</th><th>Allocation</th><th>Return date</th><th>Location</th><th>Action</th></tr></thead><tbody>
                {visible.map((item) => { const allocation = allocationFor(data, item.allocationReference); const employee = allocation && employeeFor(data, allocation.employeeId); return <tr key={item.reference}>
                  <td data-label="Return"><strong>{item.reference}</strong></td>
                  <td data-label="Employee">{employee?.employee_number} · {employeeName(employee)}</td>
                  <td data-label="Asset">{allocation && assetFor(data, allocation.assetId)?.identifier}</td>
                  <td data-label="Product">{allocation && productFor(data, allocation.assetId)?.name}</td>
                  <td data-label="Allocation">{item.allocationReference}</td><td data-label="Return date">{item.returnedOn}</td>
                  <td data-label="Location">{item.receivingLocation}</td>
                  <td data-label="Action"><button type="button" className="text-button" aria-label={'View return ' + item.reference} onClick={() => setSelected(item)}>View details</button></td>
                </tr> })}</tbody></table></div>
              <div className="workflow-pagination"><span>Showing {page * PAGE_SIZE + 1}–{page * PAGE_SIZE + visible.length} of {filtered.length} · Page {page + 1} of {Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))}</span><div><button type="button" className="button workflow-secondary" disabled={page === 0} onClick={() => setPage((value) => value - 1)}>Previous</button><button type="button" className="button workflow-secondary" disabled={(page + 1) * PAGE_SIZE >= filtered.length} onClick={() => setPage((value) => value + 1)}>Next</button></div></div>
            </> : null}
    </section>
    {selected && data && (() => { const allocation = allocationFor(data, selected.allocationReference); const employee = allocation && employeeFor(data, allocation.employeeId); return <WorkflowDialog title={selected.reference} onClose={() => setSelected(null)}>
      <p className="workflow-help">Fictional return example. It is not an operational verification or exit-clearance record.</p>
      <dl className="workflow-details">
        <div><dt>Related allocation</dt><dd>{selected.allocationReference}</dd></div>
        <div><dt>Employee</dt><dd>{employee?.employee_number} · {employeeName(employee)}</dd></div>
        <div><dt>Asset</dt><dd>{allocation && assetFor(data, allocation.assetId)?.identifier}</dd></div>
        <div><dt>Product</dt><dd>{allocation && productFor(data, allocation.assetId)?.name}</dd></div>
        <div><dt>Return date</dt><dd>{selected.returnedOn}</dd></div>
        <div><dt>Returned by</dt><dd>{selected.returnedBy}</dd></div>
        <div><dt>Verified by</dt><dd>{selected.verifiedBy} · Fictional example only</dd></div>
        <div><dt>Receiving location</dt><dd>{selected.receivingLocation} · Proposed capture</dd></div>
        <div><dt>Condition</dt><dd>{selected.conditionNote} · Vocabulary pending</dd></div>
        <div><dt>Remarks</dt><dd>{selected.remarks}</dd></div>
      </dl>
      <p className="workflow-help">No post-return lifecycle change, approval outcome or employee exit completion is inferred.</p>
    </WorkflowDialog> })()}
    {createOpen && <WorkflowDialog title="Record Return preview" onClose={() => setCreateOpen(false)}>
      <p className="workflow-help">Select a fictional current-custody example. This is not proof that a return is due or authorized. Verification and post-return state rules remain pending.</p>
      {loading || error || !data ? <p className="workflow-message">Preview sources are unavailable.</p> : <form className="workflow-form" onSubmit={(event) => event.preventDefault()}>
        <label>Search allocations<input type="search" value={allocationSearch} placeholder="DEMO allocation, employee or asset" onChange={(event) => setAllocationSearch(event.target.value)} /></label>
        <label>Select fictional allocation<select value={allocationRef} onChange={(event) => setAllocationRef(event.target.value)}><option value="">Choose an allocation</option>{allocationChoices.map((item) => <option key={item.reference} value={item.reference}>{item.reference} · {assetFor(data, item.assetId)?.identifier}</option>)}</select></label>
        {selectedAllocation && <p className="workflow-selection">{employeeName(employeeFor(data, selectedAllocation.employeeId))} · {assetFor(data, selectedAllocation.assetId)?.identifier} · {productFor(data, selectedAllocation.assetId)?.name}</p>}
        <label>Return date<input type="date" /></label>
        <label>Returned by<input type="text" placeholder="Identity from authorized context" /></label>
        <label>Verified by<input type="text" placeholder="Verifier policy pending" /></label>
        <label>Asset condition observation<textarea rows={2} placeholder="Condition vocabulary pending approval" /></label>
        <label>Remarks<textarea rows={2} placeholder="Return remarks" /></label>
        <label>Receiving location (proposed)<select defaultValue=""><option value="">Choose a fictional location</option>{locations.map((item) => <option key={item}>{item}</option>)}</select></label>
        <p className="workflow-help">Supporting documents need a reviewed storage contract. No asset is marked Available and no exit is cleared.</p>
        <button type="submit" className="button button-primary" disabled>Submit return (unavailable)</button>
      </form>}
    </WorkflowDialog>}
  </>
}
