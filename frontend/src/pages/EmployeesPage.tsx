import { useEffect, useState } from 'react'
import '../employees/employees.css'
import { PageHeader } from '../components/PageHeader'
import { EmployeeDetails } from '../employees/EmployeeDetails'
import { EmployeeDialog } from '../employees/EmployeeDialog'
import { mockEmployeeProvider } from '../employees/mockEmployeeProvider'
import type {
  Employee, EmployeeDirectoryProvider, EmployeePageResult, EmployeeSummary,
} from '../employees/types'

const PAGE_SIZE = 5

type Props = { provider?: EmployeeDirectoryProvider }

export function EmployeesPage({ provider = mockEmployeeProvider }: Props) {
  const [search, setSearch] = useState('')
  const [department, setDepartment] = useState('')
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(0)
  const [reload, setReload] = useState(0)
  const [result, setResult] = useState<EmployeePageResult | null>(null)
  const [summary, setSummary] = useState<EmployeeSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [selected, setSelected] = useState<Employee | null>(null)

  useEffect(() => {
    let current = true
    const filters = {
      q: search.trim() || undefined,
      department_id: department || undefined,
      status: status || undefined,
      limit: PAGE_SIZE,
      offset: page * PAGE_SIZE,
    }
    Promise.all([provider.listEmployees(filters), provider.getSummary()])
      .then(([nextResult, nextSummary]) => {
        if (!current) return
        setResult(nextResult)
        setSummary(nextSummary)
        setError(false)
        setLoading(false)
      })
      .catch(() => {
        if (!current) return
        setResult(null)
        setSummary(null)
        setError(true)
        setLoading(false)
      })
    return () => { current = false }
  }, [provider, search, department, status, page, reload])

  const totalPages = Math.max(1, Math.ceil((result?.total ?? 0) / PAGE_SIZE))
  const start = result && result.total > 0 ? result.offset + 1 : 0
  const end = result ? result.offset + result.items.length : 0

  return (
    <>
      <PageHeader
        eyebrow="People"
        title="Employees"
        description="Find employee profiles and their current organization. Employee records will come from an approved authoritative source in a future release."
      />
      <div className="employee-mock-banner" role="status">
        <strong>Fictional preview data</strong>
        <span> This directory is a local mock. It makes no backend requests and contains no real employee records.</span>
      </div>
      <section className="employee-sync" aria-labelledby="employee-sync-title">
        <div><p className="eyebrow">Source connection</p><h2 id="employee-sync-title">Employee synchronization</h2><p className="employee-sync-description">The authoritative employee source is not yet connected.</p></div>
        <dl className="employee-sync-status"><div><dt>Connection</dt><dd>Not connected</dd></div><div><dt>Last successful sync</dt><dd>Not available</dd></div><div><dt>Availability</dt><dd>Unavailable</dd></div></dl>
        <button className="button employee-secondary" type="button" disabled aria-describedby="employee-sync-title">Sync Employees (unavailable)</button>
      </section>
      <section className="employee-summary" aria-label="Employee summary">
        <article><span>Total employees</span><strong>{summary?.total ?? '—'}</strong></article>
        <article><span>Active</span><strong>{summary?.active ?? '—'}</strong></article>
        <article><span>Inactive</span><strong>{summary?.inactive ?? '—'}</strong></article>
        <article><span>Departments</span><strong>{summary?.departments ?? '—'}</strong></article>
      </section>
      <section className="employee-directory" aria-labelledby="employee-directory-title">
        <div className="employee-directory-heading">
          <div><p className="eyebrow">Directory</p><h2 id="employee-directory-title">Employee directory</h2></div>
          <span className="employee-mock-tag">Mock data</span>
        </div>
        <div className="employee-filters">
          <div className="employee-filter-search">
            <label htmlFor="employee-search">Search employees</label>
            <input
              id="employee-search"
              type="search"
              placeholder="Name, code, department or team"
              value={search}
              onChange={(event) => { setSearch(event.target.value); setPage(0); setLoading(true) }}
            />
          </div>
          <div>
            <label htmlFor="employee-department-filter">Department</label>
            <select
              id="employee-department-filter"
              value={department}
              onChange={(event) => { setDepartment(event.target.value); setPage(0); setLoading(true) }}
            >
              <option value="">All departments</option>
              {provider.departments.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="employee-status-filter">Employment status</label>
            <select
              id="employee-status-filter"
              value={status}
              onChange={(event) => { setStatus(event.target.value); setPage(0); setLoading(true) }}
            >
              <option value="">All statuses</option>
              {provider.statuses.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
            </select>
          </div>
        </div>
        {loading ? (
          <p className="employee-message" role="status">Loading employee preview…</p>
        ) : error ? (
          <div className="employee-message" role="alert">
            <strong>Employee preview is unavailable.</strong>
            <p>The mock provider could not load. No live data was requested.</p>
            <button type="button" className="button employee-secondary" onClick={() => { setLoading(true); setReload((value) => value + 1) }}>Try again</button>
          </div>
        ) : result && result.items.length === 0 ? (
          <div className="employee-message"><strong>No employees found.</strong><p>Try another search or filter.</p></div>
        ) : result ? (
          <>
            <div className="employee-table-wrap">
              <table className="employee-table">
                <caption className="sr-only">Fictional employee directory</caption>
                <thead><tr>
                  <th scope="col">Employee</th><th scope="col">Code</th><th scope="col">Department</th>
                  <th scope="col">Team</th><th scope="col">Designation</th><th scope="col">Status</th>
                  <th scope="col">Action</th>
                </tr></thead>
                <tbody>
                  {result.items.map((employee) => {
                    const name = employee.first_name + ' ' + employee.last_name
                    return (
                      <tr key={employee.id}>
                        <td data-label="Employee"><strong>{name}</strong></td>
                        <td data-label="Code">{employee.employee_number}</td>
                        <td data-label="Department">{provider.departments.find((item) => item.id === employee.department_id)?.name ?? 'Not recorded'}</td>
                        <td data-label="Team">{provider.teams.find((item) => item.id === employee.team_id)?.name ?? 'Not recorded'}</td>
                        <td data-label="Designation">{provider.designations.find((item) => item.id === employee.designation_id)?.name ?? 'Not recorded'}</td>
                        <td data-label="Status"><span className={'employee-status employee-status-' + employee.status}>{provider.statuses.find((item) => item.value === employee.status)?.label ?? employee.status}</span></td>
                        <td data-label="Action">
                          <button type="button" className="text-button" aria-label={'View details for ' + name} onClick={() => setSelected(employee)}>View details</button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            <div className="employee-pagination">
              <span>Showing {start}–{end} of {result.total} · Page {page + 1} of {totalPages}</span>
              <div>
                <button className="button employee-secondary" type="button" disabled={page === 0} onClick={() => { setPage((value) => value - 1); setLoading(true) }}>Previous</button>
                <button className="button employee-secondary" type="button" disabled={page + 1 >= totalPages} onClick={() => { setPage((value) => value + 1); setLoading(true) }}>Next</button>
              </div>
            </div>
          </>
        ) : null}
      </section>
      {selected && (
        <EmployeeDialog title={selected.first_name + ' ' + selected.last_name} onClose={() => setSelected(null)}>
          <EmployeeDetails employee={selected} provider={provider} />
        </EmployeeDialog>
      )}
    </>
  )
}
