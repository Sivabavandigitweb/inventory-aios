import { PageHeader } from '../components/PageHeader'

const metrics = [
  { label: 'Total assets', value: '—', tone: 'blue' },
  { label: 'Available', value: '—', tone: 'green' },
  { label: 'Under repair', value: '—', tone: 'orange' },
  { label: 'Pending approvals', value: '—', tone: 'purple' },
]

export function DashboardPage() {
  return (
    <>
      <PageHeader
        eyebrow="Overview"
        title="Good morning, Admin"
        description="A clear view of your inventory operations will appear here once the data services are connected."
        action={<button className="button button-primary" type="button">＋ Quick action</button>}
      />
      <section className="metric-grid" aria-label="Inventory summary">
        {metrics.map((metric) => (
          <article className="metric-card" key={metric.label}>
            <div className={`metric-icon ${metric.tone}`} aria-hidden="true">•</div>
            <div><p>{metric.label}</p><strong>{metric.value}</strong></div>
            <span className="metric-placeholder">Awaiting data</span>
          </article>
        ))}
      </section>
      <div className="dashboard-grid">
        <section className="panel" aria-labelledby="activity-title">
          <div className="panel-heading"><div><p className="eyebrow">Recent activity</p><h2 id="activity-title">Activity feed</h2></div><button className="text-button" type="button">View all</button></div>
          <div className="empty-state"><span className="empty-state-icon" aria-hidden="true">◌</span><strong>No activity yet</strong><p>Inventory events will be listed here when the backend is connected.</p></div>
        </section>
        <section className="panel" aria-labelledby="tasks-title">
          <div className="panel-heading"><div><p className="eyebrow">Attention needed</p><h2 id="tasks-title">Open tasks</h2></div></div>
          <ul className="task-list"><li><span className="task-dot blue" /><div><strong>Pending registrations</strong><small>Newly received assets</small></div><span className="task-count">—</span></li><li><span className="task-dot orange" /><div><strong>Asset returns</strong><small>Awaiting verification</small></div><span className="task-count">—</span></li><li><span className="task-dot purple" /><div><strong>Approvals</strong><small>Requests in your queue</small></div><span className="task-count">—</span></li></ul>
        </section>
      </div>
    </>
  )
}