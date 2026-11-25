import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { mockAssetProvider } from '../assets/mockAssetProvider'
import type { AssetPreviewProvider } from '../assets/types'
import { PageHeader } from '../components/PageHeader'
import { mockEmployeeProvider } from '../employees/mockEmployeeProvider'
import type { EmployeeDirectoryProvider } from '../employees/types'
import { buildDashboardSummary, type CountItem, type DashboardSummary } from '../dashboard/selectors'
import '../dashboard/dashboard.css'

type DashboardProps = {
  assetProvider?: AssetPreviewProvider
  employeeProvider?: EmployeeDirectoryProvider
}

function CountBars({ items, total, variant }: { items: CountItem[]; total: number; variant: 'lifecycle' | 'category' | 'location' }) {
  if (total === 0) return <p className="dashboard-empty">No individual assets in this preview.</p>
  return <ul className="dashboard-bars" aria-label={variant + ' distribution'}>
    {items.map((item) => <li key={item.label}>
      <div className="dashboard-bar-label"><span>{item.label}</span><strong>{item.count}</strong></div>
      <div className="dashboard-track" aria-hidden="true">
        <span className={'dashboard-fill dashboard-fill-' + (variant === 'lifecycle' ? item.label.toLowerCase() : variant)}
          style={{ width: (item.count / total * 100) + '%' }} />
      </div>
    </li>)}
  </ul>
}

export function DashboardPage({
  assetProvider = mockAssetProvider, employeeProvider = mockEmployeeProvider,
}: DashboardProps) {
  const [summary, setSummary] = useState<DashboardSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [retry, setRetry] = useState(0)

  useEffect(() => {
    let current = true
    Promise.all([assetProvider.load(), employeeProvider.getSummary()])
      .then(([assets, employees]) => {
        if (!current) return
        setSummary(buildDashboardSummary(assets, employees))
        setError(false)
        setLoading(false)
      })
      .catch(() => {
        if (!current) return
        setSummary(null)
        setError(true)
        setLoading(false)
      })
    return () => { current = false }
  }, [assetProvider, employeeProvider, retry])

  const count = (status: string) => summary?.lifecycle.find((item) => item.label === status)?.count ?? 0

  return <>
    <PageHeader eyebrow="Overview" title="Inventory dashboard"
      description="A local overview of fictional asset and employee records. Operational metrics will appear after authorized services are connected." />
    <div className="dashboard-preview-banner" role="status">
      <strong>Fictional preview data</strong> · DEMO records only. No backend requests or live company records.
    </div>
    {loading ? <div className="dashboard-state" role="status">Loading dashboard preview…</div>
      : error ? <div className="dashboard-state" role="alert">
        <strong>Dashboard preview is unavailable.</strong>
        <p>The local provider could not load. No live data was requested.</p>
        <button type="button" className="button dashboard-secondary" onClick={() => { setLoading(true); setRetry((value) => value + 1) }}>Try again</button>
      </div>
        : summary ? <>
          <section className="dashboard-summary" aria-label="Inventory summary">
            <article><span>Individual assets</span><strong>{summary.totalAssets}</strong><small>Separate from quantity stock</small></article>
            <article><span>Available assets</span><strong>{count('Available')}</strong><small>Individual units</small></article>
            <article><span>Allocated assets</span><strong>{count('Allocated')}</strong><small>Individual units</small></article>
            <article><span>Employees</span><strong>{summary.employees.total}</strong><small>Fictional directory</small></article>
          </section>
          <div className="dashboard-panels">
            <section className="dashboard-panel" aria-labelledby="lifecycle-title">
              <p className="eyebrow">Individual asset status</p><h2 id="lifecycle-title">Lifecycle distribution</h2>
              <p className="dashboard-context">All five R-02 statuses; {summary.totalAssets} individual assets in total.</p>
              <CountBars items={summary.lifecycle} total={summary.totalAssets} variant="lifecycle" />
            </section>
            <section className="dashboard-panel" aria-labelledby="stock-title">
              <p className="eyebrow">Separate stock view</p><h2 id="stock-title">Quantity stock availability</h2>
              <p className="dashboard-context">Illustrative whole counts by lot. Units are unapproved, so different products are not totaled together.</p>
              {summary.stock.length ? <ul className="dashboard-stock" aria-label="Stock availability by lot">
                {summary.stock.map((lot) => <li key={lot.reference}>
                  <div className="dashboard-bar-label"><span><strong>{lot.product}</strong> · {lot.location}<small>{lot.reference}</small></span><b>{lot.available} available</b></div>
                  <div className="dashboard-track" aria-hidden="true">
                    <span className="dashboard-fill dashboard-fill-stock" style={{ width: (lot.physical > 0 ? lot.available / lot.physical * 100 : 0) + '%' }} />
                  </div>
                  <span className="dashboard-stock-detail">{lot.physical} physical · {lot.reserved} reserved</span>
                </li>)}
              </ul> : <p className="dashboard-empty">No quantity stock in this preview.</p>}
            </section>
            <section className="dashboard-panel" aria-labelledby="categories-title">
              <p className="eyebrow">Individual assets only</p><h2 id="categories-title">Asset categories</h2>
              <CountBars items={summary.categories} total={summary.totalAssets} variant="category" />
            </section>
            <section className="dashboard-panel" aria-labelledby="locations-title">
              <p className="eyebrow">Individual assets only</p><h2 id="locations-title">Asset locations</h2>
              <CountBars items={summary.locations} total={summary.totalAssets} variant="location" />
            </section>
          </div>
          <div className="dashboard-lower">
            <section className="dashboard-panel" aria-labelledby="people-title">
              <p className="eyebrow">People</p><h2 id="people-title">Employee overview</h2>
              <dl className="dashboard-people">
                <div><dt>Total</dt><dd>{summary.employees.total}</dd></div>
                <div><dt>Active</dt><dd>{summary.employees.active}</dd></div>
                <div><dt>Inactive</dt><dd>{summary.employees.inactive}</dd></div>
                <div><dt>Departments</dt><dd>{summary.employees.departments}</dd></div>
              </dl>
              <p className="dashboard-context">New joiners, departures and exit clearance are unavailable without approved source and workflow data.</p>
            </section>
            <section className="dashboard-panel" aria-labelledby="sync-title">
              <p className="eyebrow">Source connection</p><h2 id="sync-title">Employee synchronization</h2>
              <dl className="dashboard-sync">
                <div><dt>Connection</dt><dd>Not connected</dd></div>
                <div><dt>Last successful sync</dt><dd>Not available</dd></div>
                <div><dt>Availability</dt><dd>Unavailable</dd></div>
              </dl>
              <p className="dashboard-context">The authoritative employee source has not been connected.</p>
            </section>
          </div>
          <div className="dashboard-lower">
            <nav className="dashboard-panel dashboard-links" aria-label="Quick navigation">
              <p className="eyebrow">Explore previews</p><h2>Quick navigation</h2>
              <Link to="/assets?section=assets">Asset directory <span aria-hidden="true">→</span></Link>
              <Link to="/assets?section=quantity">Quantity inventory <span aria-hidden="true">→</span></Link>
              <Link to="/assets?section=products">Product catalog <span aria-hidden="true">→</span></Link>
              <Link to="/employees">Employee directory <span aria-hidden="true">→</span></Link>
              <Link to="/exit-clearance">Exit clearance preview <span aria-hidden="true">→</span></Link>
              <Link to="/approvals">Approvals preview <span aria-hidden="true">→</span></Link>
              <Link to="/reports">Reports preview <span aria-hidden="true">&gt;</span></Link>
              <Link to="/repairs">Repairs preview <span aria-hidden="true">→</span></Link>
            </nav>
            <section className="dashboard-panel" aria-labelledby="operations-title">
              <p className="eyebrow">Not connected</p><h2 id="operations-title">Operational activity and pending actions</h2>
              <ul className="dashboard-unavailable">
                <li>Pending approvals — unavailable</li>
                <li>Overdue returns — unavailable</li>
                <li>Active repair workflows — unavailable</li>
                <li>Recent inventory transactions — unavailable</li>
                <li>Employee exit clearance — unavailable</li>
              </ul>
              <p className="dashboard-context">No operational records or zero counts are inferred from preview data.</p>
            </section>
          </div>
        </> : null}
  </>
}
