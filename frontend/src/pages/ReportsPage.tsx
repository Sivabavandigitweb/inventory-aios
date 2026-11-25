import { useMemo, useState } from 'react'
import '../reports/reports.css'
import { Link } from 'react-router-dom'
import { PageHeader } from '../components/PageHeader'
import { REPORTS, buildReportRows, type ReportKind, type ReportRow } from '../reports/selectors'
import { useReportsPreview, type ReportsProviders } from '../reports/useReportsPreview'

const PAGE_SIZE = 6
const options = (rows: ReportRow[], field: keyof ReportRow) => [...new Set(rows.map((row) => row[field]).filter((value) => typeof value === 'string' && value.length > 0))].sort()
function FilterSelect({ label, value, values, onChange }: { label: string; value: string; values: string[]; onChange: (value: string) => void }) {
  return <label>{label}<select aria-label={label} value={value} onChange={(event) => onChange(event.target.value)}><option value="">All</option>{values.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
}
function StatusBars({ rows }: { rows: ReportRow[] }) {
  const counts = new Map<string, number>()
  rows.forEach((row) => counts.set(row.status, (counts.get(row.status) ?? 0) + 1))
  const max = Math.max(1, rows.length)
  return <section className="report-chart" aria-label="Asset status summary">
    <h3>Current preview status</h3>
    {counts.size ? <ul>{[...counts].map(([status, count]) => <li key={status}><div><span>{status}</span><strong>{count}</strong></div><span className="report-track" aria-hidden="true"><span style={{ width: (count / max * 100) + '%' }} /></span></li>)}</ul> : <p>No status values in this filtered preview.</p>}
    <p>Numeric table results remain available to assistive technology.</p>
  </section>
}
function RelatedLink({ row }: { row: ReportRow }) { return <Link to={row.href}>Open preview</Link> }
export function ReportsPage(props: ReportsProviders) {
  const preview = useReportsPreview(props)
  const [kind, setKind] = useState<ReportKind>('assets')
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState('')
  const [location, setLocation] = useState('')
  const [status, setStatus] = useState('')
  const [department, setDepartment] = useState('')
  const [employee, setEmployee] = useState('')
  const [fromDate, setFromDate] = useState('')
  const [toDate, setToDate] = useState('')
  const [page, setPage] = useState(0)
  const data = preview.data
  const definition = REPORTS.find((item) => item.id === kind)!
  const allRows = useMemo(() => data ? buildReportRows(kind, data) : [], [data, kind])
  const filtered = useMemo(() => allRows.filter((row) => {
    const searchable = [row.reference, row.subject, row.details, row.category, row.location, row.status, row.employee, row.department].join(' ').toLowerCase()
    return searchable.includes(query.toLowerCase())
      && (!category || row.category === category) && (!location || row.location === location)
      && (!status || row.status === status) && (!department || row.department === department)
      && (!employee || row.employee === employee)
      && (!fromDate || (row.date && row.date >= fromDate)) && (!toDate || (row.date && row.date <= toDate))
  }), [allRows, query, category, location, status, department, employee, fromDate, toDate])
  const visible = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)
  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const setFilter = (setter: (value: string) => void) => (value: string) => { setter(value); setPage(0) }
  function changeKind(value: string) {
    setKind(value as ReportKind); setQuery(''); setCategory(''); setLocation(''); setStatus(''); setDepartment(''); setEmployee(''); setFromDate(''); setToDate(''); setPage(0)
  }
  const summaryText = kind === 'quantity'
    ? 'Availability is shown per lot as physical minus reserved. Illustrative whole counts only; units are unapproved and lots/products are not added together.'
    : kind === 'returns'
      ? 'Return rows are historical examples; a recorded example does not establish verification or current clearance.'
      : kind === 'exit'
        ? 'Clearance examples are partial; no visible count establishes exit readiness.'
        : 'Rows come from partial fictional module previews and are not complete company records.'
  const columns = useMemo(() => {
    const base: { label: string; field: keyof ReportRow }[] = [{ label: 'Reference', field: 'reference' }, { label: 'Record', field: 'subject' }, { label: 'Details', field: 'details' }]
    if (allRows.some((row) => row.category)) base.push({ label: 'Category', field: 'category' })
    if (allRows.some((row) => row.location)) base.push({ label: 'Location', field: 'location' })
    if (allRows.some((row) => row.employee)) base.push({ label: 'Employee', field: 'employee' })
    if (allRows.some((row) => row.department)) base.push({ label: 'Department', field: 'department' })
    if (allRows.some((row) => row.status)) base.push({ label: 'Preview status', field: 'status' })
    if (allRows.some((row) => row.date)) base.push({ label: 'Example date', field: 'date' })
    return base
  }, [allRows])
  return <>
    <PageHeader eyebrow="Insights" title="Reports and Analytics" description="Explore searchable report previews built from shared fictional module records. Operational report services and exports are unavailable." />
    <div className="report-banner" role="status"><strong>Fictional, partial preview data</strong> - DEMO records only. Reports are not operational, complete, or permission-filtered.</div>
    {preview.loading ? <div className="report-state" role="status">Loading report preview...</div>
      : preview.error ? <div className="report-state" role="alert"><strong>Report preview is unavailable.</strong><p>A shared local provider or reference check failed. No live data was requested.</p><button className="button report-secondary" type="button" onClick={preview.retry}>Try again</button></div>
        : data ? <section className="report-panel" aria-label="Report preview">
          <div className="report-toolbar">
            <label>Report category<select aria-label="Report category" value={kind} onChange={(event) => changeKind(event.target.value)}>{REPORTS.map((item) => <option key={item.id} value={item.id}>{item.label} - {item.requirement}</option>)}</select></label>
            <button className="button report-secondary" type="button" disabled title="Operational export is not connected">Export Excel (unavailable)</button>
            <button className="button report-secondary" type="button" disabled title="Operational export is not connected">Export PDF (unavailable)</button>
          </div>
          {!definition.available ? <div className="report-unavailable" role="status"><h2>{definition.label} unavailable</h2><p>{definition.reason}</p><p>This report category is identified in requirements, but the preview lacks approved semantics or data.</p></div> : <>
            <section className="report-summary" aria-label="Filtered report summary">
              <article><span>Matching preview rows</span><strong>{filtered.length}</strong></article>
              <article><span>Page</span><strong>{page + 1} / {totalPages}</strong></article>
              <article><span>Source coverage</span><strong>Partial</strong></article>
            </section>
            <p className="report-context">{summaryText}</p>
            <div className="report-filters">
              <label>Search<input aria-label="Search report" type="search" value={query} onChange={(event) => setFilter(setQuery)(event.target.value)} placeholder="Search report rows" /></label>
              {allRows.some((row) => row.category) && <FilterSelect label="Category" value={category} values={options(allRows, 'category')} onChange={setFilter(setCategory)} />}
              {allRows.some((row) => row.location) && <FilterSelect label="Location" value={location} values={options(allRows, 'location')} onChange={setFilter(setLocation)} />}
              {allRows.some((row) => row.status) && <FilterSelect label="Lifecycle or preview status" value={status} values={options(allRows, 'status')} onChange={setFilter(setStatus)} />}
              {allRows.some((row) => row.department) && <FilterSelect label="Department" value={department} values={options(allRows, 'department')} onChange={setFilter(setDepartment)} />}
              {allRows.some((row) => row.employee) && <FilterSelect label="Employee" value={employee} values={options(allRows, 'employee')} onChange={setFilter(setEmployee)} />}
              {allRows.some((row) => row.date) && <><label>From date<input aria-label="From date" type="date" value={fromDate} onChange={(event) => setFilter(setFromDate)(event.target.value)} /></label><label>To date<input aria-label="To date" type="date" value={toDate} onChange={(event) => setFilter(setToDate)(event.target.value)} /></label></>}
            </div>
            {kind === 'assets' && <StatusBars rows={filtered} />}
            {!visible.length ? <p className="report-state">{allRows.length ? 'No rows match the selected filters.' : 'No rows are available for this preview category.'}</p> : <div className="report-table-wrap"><table className="report-table"><caption className="sr-only">{definition.label} fictional report preview</caption><thead><tr>{columns.map((column) => <th key={column.field}>{column.label}</th>)}<th>Related module</th></tr></thead><tbody>{visible.map((row) => <tr key={row.id}>{columns.map((column) => <td key={column.field} data-label={column.label}>{String(row[column.field] || 'Not available')}</td>)}<td data-label="Related module"><RelatedLink row={row} /></td></tr>)}</tbody></table></div>}
            <div className="report-pagination"><span>Showing {filtered.length ? page * PAGE_SIZE + 1 : 0}-{Math.min((page + 1) * PAGE_SIZE, filtered.length)} of {filtered.length} filtered rows (from {allRows.length} preview rows)</span><div><button className="button report-secondary" type="button" disabled={page === 0} onClick={() => setPage((value) => value - 1)}>Previous</button><button className="button report-secondary" type="button" disabled={page + 1 >= totalPages} onClick={() => setPage((value) => value + 1)}>Next</button></div></div>
          </>}
        </section> : null}
  </>
}
