import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { PageHeader } from '../components/PageHeader'
import { mockEmployeeProvider } from '../employees/mockEmployeeProvider'
import type { Employee, EmployeeDirectoryProvider } from '../employees/types'
import { WorkflowDialog } from '../workflows/WorkflowDialog'
import type { ExitClearancePreviewCase } from '../exitClearance/types'
import { clearanceCaseSummary } from '../exitClearance/selectors'
import { useExitClearancePreview, type ExitClearanceProviders } from '../exitClearance/useExitClearancePreview'
import '../workflows/workflows.css'
import '../exitClearance/exitClearance.css'
const PAGE_SIZE = 5
function fullName(employee: Employee) { return employee.first_name + ' ' + employee.last_name }
function optionName(options: readonly { id: string; name: string }[], id: string | null) { return options.find((item) => item.id === id)?.name ?? 'Not recorded' }
function ClearanceDetails({ item, employee, data, provider, close }: { item: ExitClearancePreviewCase; employee: Employee; provider: EmployeeDirectoryProvider; data: NonNullable<ReturnType<typeof useExitClearancePreview>['data']>; close: () => void }) {
  const summary = clearanceCaseSummary(data, item)
  const department = optionName(provider.departments, employee.department_id)
  const designation = optionName(provider.designations, employee.designation_id)
  return <WorkflowDialog title={item.reference} onClose={close}>
    <p className="workflow-help">Fictional partial inventory review only. Employment status and inventory clearance are separate; neither one proves the other.</p>
    <dl className="workflow-details">
      <div><dt>Employee</dt><dd>{fullName(employee)} ({employee.employee_number})</dd></div>
      <div><dt>Department / designation</dt><dd>{department} / {designation}</dd></div>
      <div><dt>Employee master status (mock)</dt><dd>{provider.statuses.find((item) => item.value === employee.status)?.label ?? employee.status}</dd></div>
      <div><dt>External employment status</dt><dd>Not connected or independently confirmed</dd></div>
      <div><dt>Outstanding individual assets in visible preview</dt><dd>{summary.outstanding.length}</dd></div>
      <div><dt>Inventory clearance readiness</dt><dd>Unknown - partial data and verification are not established</dd></div>
    </dl>
    <section className="clearance-section"><h3>Allocation and return review</h3>
      {!summary.allocations.length ? <p>No allocation records are visible for this employee in the partial preview.</p> : <ul className="clearance-list">{summary.allocations.map(({ allocation, returned, asset, outstanding }) => <li key={allocation.reference}>
        <strong>{asset?.identifier ?? 'Unknown asset'} - {allocation.reference}</strong><br />
        {outstanding ? <><span>Outstanding custody example; no related return is present.</span> <Link to={'/allocations?employee=' + encodeURIComponent(employee.employee_number)}>Allocation preview</Link></> : <><span>Return {returned?.reference} recorded on {returned?.returnedOn}; verifier field in fictional fixture: {returned?.verifiedBy}. Actual verification is unknown.</span> <Link to={'/returns?allocation=' + encodeURIComponent(allocation.reference)}>Return preview</Link></>}
      </li>)}</ul>}
      <p>A recorded return is not treated here as proof that a return was verified or that custody obligations are cleared.</p>
    </section>
    <section className="clearance-section"><h3>Proposed inventory checklist</h3><ul className="clearance-list">
      <li>{summary.outstanding.length ? 'Outstanding tracked assets must be returned before exit completion (R-07).' : 'No outstanding tracked assets are visible; partial coverage does not establish readiness.'}</li>
      <li>Return verification and inspection evidence: unknown in this preview.</li>
      <li>Quantity-stock obligations: unavailable; no quantity clearance records are connected.</li>
      <li>External employment source and exit event: not connected; this example is not an employment decision.</li>
      <li>Approval authority and audit history: unavailable.</li>
    </ul></section>
    <button className="button button-primary" type="button" disabled title="Operational clearance is unavailable">Complete inventory clearance (unavailable)</button>
  </WorkflowDialog>
}
export function ExitClearancePage({ assetProvider, employeeProvider, workflowProvider, clearanceProvider }: ExitClearanceProviders) {
  const preview = useExitClearancePreview({ assetProvider, employeeProvider, workflowProvider, clearanceProvider })
  const directoryProvider = employeeProvider ?? mockEmployeeProvider
  const [query, setQuery] = useState(() => new URLSearchParams(window.location.search).get('employee') ?? '')
  const [department, setDepartment] = useState('')
  const [view, setView] = useState('')
  const [page, setPage] = useState(0)
  const [selected, setSelected] = useState<ExitClearancePreviewCase | null>(null)
  const data = preview.data
  const rows = useMemo(() => {
    if (!data) return []
    return data.clearance.cases.filter((item) => {
      const employee = data.employees.find((entry) => entry.id === item.employeeId)
      if (!employee) return false
      const summary = clearanceCaseSummary(data, item)
      const search = [item.reference, employee.employee_number, fullName(employee), optionName(directoryProvider.departments, employee.department_id), optionName(directoryProvider.designations, employee.designation_id)].join(' ').toLowerCase()
      const needsVerification = summary.returns.length > 0
      return search.includes(query.toLowerCase()) && (!department || employee.department_id === department)
        && (!view || (view === 'outstanding' ? summary.outstanding.length > 0 : view === 'verification' ? needsVerification : true))
    })
  }, [data, query, department, view, directoryProvider])
  const totalPages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE))
  const visible = rows.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)
  const outstandingCases = data?.clearance.cases.filter((item) => clearanceCaseSummary(data, item).outstanding.length > 0).length ?? 0
  const unknownCases = data?.clearance.cases.length ?? 0
  const selectedEmployee = selected ? data?.employees.find((employee) => employee.id === selected.employeeId) : undefined
  return <>
    <PageHeader eyebrow="Employee lifecycle" title="Exit Clearance" description="Review fictional inventory custody examples. Employee departure and inventory clearance are separate processes." />
    <div className="workflow-banner" role="status"><strong>Fictional, partial preview data</strong> - DEMO records only; no actual exit cases or source events are connected.</div>
    {preview.loading ? <div className="workflow-message" role="status">Loading clearance preview...</div>
      : preview.error ? <div className="workflow-message" role="alert"><strong>Clearance preview is unavailable.</strong><p>A local provider could not load. No live data was requested.</p><button className="button workflow-secondary" type="button" onClick={preview.retry}>Try again</button></div>
        : data ? <>
          <section className="clearance-summary" aria-label="Clearance preview summary">
            <article><span>Fictional review examples</span><strong>{data.clearance.cases.length}</strong></article>
            <article><span>Examples with visible outstanding assets</span><strong>{outstandingCases}</strong></article>
            <article><span>Readiness not established</span><strong>{unknownCases}</strong></article>
          </section>
          <section className="workflow-panel" aria-labelledby="clearance-directory-title">
            <div className="workflow-heading"><div><p className="eyebrow">R-07 preview</p><h2 id="clearance-directory-title">Inventory clearance review</h2></div><span className="workflow-tag">Completion unavailable</span></div>
            <div className="clearance-section" style={{ marginTop: 0, paddingTop: 0, borderTop: 0 }}><h3>Employee source connection</h3><p>Not connected. No last synchronization time or external departure status is available.</p></div>
            <p className="clearance-note">Inactive in the fictional employee directory does not mean departing; a departure does not mean inventory-cleared. Missing source records never cause deletion or automatic clearance.</p>
            <div className="clearance-toolbar">
              <label>Search clearance examples<input type="search" aria-label="Search clearance examples" value={query} onChange={(event) => { setQuery(event.target.value); setPage(0) }} placeholder="Employee, code, department or reference" /></label>
              <label>Department<select aria-label="Department" value={department} onChange={(event) => { setDepartment(event.target.value); setPage(0) }}><option value="">All departments</option>{directoryProvider.departments.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
              <label>Clearance view<select aria-label="Clearance view" value={view} onChange={(event) => { setView(event.target.value); setPage(0) }}><option value="">All review examples</option><option value="outstanding">Visible outstanding assets</option><option value="verification">Return verification unknown</option></select></label>
            </div>
            {!visible.length ? <p className="workflow-message">{data.clearance.cases.length ? 'No clearance examples match these filters.' : 'No clearance examples are available.'}</p> : <div className="workflow-table-wrap"><table className="workflow-table"><caption className="sr-only">Fictional employee clearance directory</caption><thead><tr><th>Review reference</th><th>Employee</th><th>Department / designation</th><th>Master status (mock)</th><th>Outstanding assets</th><th>Readiness</th><th>Action</th></tr></thead><tbody>{visible.map((item) => { const employee = data.employees.find((entry) => entry.id === item.employeeId)!; const summary = clearanceCaseSummary(data, item); return <tr key={item.reference}><td data-label="Review reference"><strong>{item.reference}</strong></td><td data-label="Employee">{fullName(employee)}<br />{employee.employee_number}</td><td data-label="Department / designation">{optionName(directoryProvider.departments, employee.department_id)}<br />{optionName(directoryProvider.designations, employee.designation_id)}</td><td data-label="Master status (mock)"><span className="clearance-badge clearance-badge-neutral">{directoryProvider.statuses.find((status) => status.value === employee.status)?.label ?? employee.status}</span></td><td data-label="Outstanding assets">{summary.outstanding.length || 'None visible'}</td><td data-label="Readiness"><span className="clearance-badge">Unknown</span></td><td data-label="Action"><button className="text-button" type="button" aria-label={'View clearance ' + item.reference} onClick={() => setSelected(item)}>Details</button></td></tr> })}</tbody></table></div>}
            <div className="workflow-pagination"><span>Showing {rows.length ? page * PAGE_SIZE + 1 : 0} - {Math.min((page + 1) * PAGE_SIZE, rows.length)} of {rows.length} - Page {page + 1} of {totalPages}</span><div><button className="button workflow-secondary" type="button" disabled={page === 0} onClick={() => setPage((value) => value - 1)}>Previous</button><button className="button workflow-secondary" type="button" disabled={page + 1 >= totalPages} onClick={() => setPage((value) => value + 1)}>Next</button></div></div>
          </section>
        </> : null}
    {selected && selectedEmployee && data && <ClearanceDetails item={selected} employee={selectedEmployee} provider={directoryProvider} data={data} close={() => setSelected(null)} />}
  </>
}
