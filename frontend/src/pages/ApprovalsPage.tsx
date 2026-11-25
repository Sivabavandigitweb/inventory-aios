import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { PageHeader } from '../components/PageHeader'
import { WorkflowDialog } from '../workflows/WorkflowDialog'
import { useApprovalPreview, type ApprovalPreviewProviders } from '../approvals/useApprovalPreview'
import type { ApprovalPreviewRequest, NotificationCategory, NotificationPreview } from '../approvals/types'
import '../workflows/workflows.css'
import '../approvals/approvals.css'
const PAGE_SIZE = 3
type Section = 'requests' | 'notifications'
const requestTypes = ['Asset registration', 'Allocation', 'Return', 'Disposal'] as const
const notificationCategories: NotificationCategory[] = ['Pending asset registration', 'Assets pending return', 'Warranty expiration', 'Pending approvals', 'Missing asset information']
function initialSection(): Section { return new URLSearchParams(window.location.search).get('section') === 'notifications' ? 'notifications' : 'requests' }
function requestRelated(request: ApprovalPreviewRequest, data: NonNullable<ReturnType<typeof useApprovalPreview>['data']>) {
  if (request.receiptId) { const receipt = data.assets.receipts.find((item) => item.id === request.receiptId); return receipt ? 'Receipt preview ' + receipt.receivedDate : 'Receipt preview' }
  if (request.allocationReference) return request.allocationReference
  if (request.assetId) return data.assets.assets.find((item) => item.id === request.assetId)?.identifier ?? 'Asset preview'
  return 'No linked preview record'
}
function ApprovalDetails({ request, data, close }: { request: ApprovalPreviewRequest; data: NonNullable<ReturnType<typeof useApprovalPreview>['data']>; close: () => void }) {
  const employee = data.employees.find((item) => item.id === request.employeeId)
  const asset = data.assets.assets.find((item) => item.id === request.assetId)
  return <WorkflowDialog title={request.reference} onClose={close}>
    <p className="workflow-help">Fictional example only. It is not a submitted or pending operational approval request.</p>
    <dl className="workflow-details">
      <div><dt>Request type</dt><dd>{request.requestType}</dd></div><div><dt>Example date</dt><dd>{request.requestDate}</dd></div>
      <div><dt>Related preview</dt><dd>{requestRelated(request, data)}</dd></div><div><dt>Asset</dt><dd>{asset?.identifier ?? 'Not linked'}</dd></div>
      <div><dt>Employee</dt><dd>{employee ? employee.first_name + ' ' + employee.last_name + ' (' + employee.employee_number + ')' : 'Not linked'}</dd></div>
      <div><dt>Preview state</dt><dd>Illustrative only</dd></div>
    </dl>
    <p className="workflow-selection">{request.description}</p>
    {request.receiptId && <Link className="workflow-preview-link" to="/assets?section=receiving">Open receiving preview</Link>}
    {request.allocationReference && <Link className="workflow-preview-link" to={'/allocations?asset=' + encodeURIComponent(asset?.identifier ?? '')}>Open allocation preview</Link>}
    {request.employeeId && !request.allocationReference && <Link className="workflow-preview-link" to="/employees">Open employee directory</Link>}
    {request.requestType === 'Disposal' && <Link className="workflow-preview-link" to="/assets?section=assets">Open asset directory</Link>}
    <section className="approval-details-section"><h3>Proposed review requirements</h3><p>Request-type mapping, required evidence and the decision checklist need approved policy.</p></section>
    <section className="approval-details-section"><h3>Authority and remarks</h3><p>Approver authority is not configured. Future decision remarks are unavailable.</p></section>
    <section className="approval-details-section"><h3>Audit history</h3><p>No decision or audit event is recorded in this preview.</p></section>
    <div className="approval-actions"><button className="button button-primary" type="button" disabled title="Operational approval is unavailable">Approve (unavailable)</button><button className="button workflow-secondary" type="button" disabled title="Operational rejection is unavailable">Reject (unavailable)</button></div>
  </WorkflowDialog>
}
function NotificationRelated({ item, data, openRequest }: { item: NotificationPreview; data: NonNullable<ReturnType<typeof useApprovalPreview>['data']>; openRequest: (reference: string) => void }) {
  if (item.approvalReference) return <button className="text-button" type="button" onClick={() => openRequest(item.approvalReference!)}>View approval example</button>
  if (item.receiptId) return <Link to="/assets?section=receiving">Receipt preview</Link>
  if (item.allocationReference) return <Link to={'/returns?allocation=' + encodeURIComponent(item.allocationReference)}>Return preview</Link>
  if (item.assetId) { const asset = data.assets.assets.find((entry) => entry.id === item.assetId); return <Link to="/assets?section=assets">{asset?.identifier ?? 'Asset preview'}</Link> }
  return <span>None in this preview</span>
}
export function ApprovalsPage({ assetProvider, employeeProvider, workflowProvider, approvalProvider }: ApprovalPreviewProviders) {
  const preview = useApprovalPreview({ assetProvider, employeeProvider, workflowProvider, approvalProvider })
  const [section, setSection] = useState<Section>(initialSection)
  const [requestQuery, setRequestQuery] = useState('')
  const [requestType, setRequestType] = useState('')
  const [requestState, setRequestState] = useState('')
  const [notificationQuery, setNotificationQuery] = useState('')
  const [notificationCategory, setNotificationCategory] = useState('')
  const [page, setPage] = useState(0)
  const [selected, setSelected] = useState<ApprovalPreviewRequest | null>(null)
  const data = preview.data
  const requests = useMemo(() => data?.preview.requests.filter((item) => {
    const text = [item.reference, item.requestType, item.description, requestRelated(item, data!)].join(' ').toLowerCase()
    return text.includes(requestQuery.toLowerCase()) && (!requestType || item.requestType === requestType) && (!requestState || requestState === 'example')
  }) ?? [], [data, requestQuery, requestType, requestState])
  const notifications = useMemo(() => data?.preview.notifications.filter((item) => [item.reference, item.title, item.category, item.description].join(' ').toLowerCase().includes(notificationQuery.toLowerCase()) && (!notificationCategory || item.category === notificationCategory)) ?? [], [data, notificationQuery, notificationCategory])
  const visibleRequests = requests.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)
  const visibleNotifications = notifications.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)
  const currentRows = section === 'requests' ? requests : notifications
  const pages = Math.max(1, Math.ceil(currentRows.length / PAGE_SIZE))
  const openRequest = (reference: string) => { const found = data?.preview.requests.find((item) => item.reference === reference); if (found) { setSection('requests'); setSelected(found) } }
  const tabs: { id: Section; label: string }[] = [{ id: 'requests', label: 'Approval requests' }, { id: 'notifications', label: 'Notifications' }]
  function tabKey(event: React.KeyboardEvent<HTMLButtonElement>) {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
    event.preventDefault()
    const index = tabs.findIndex((tab) => tab.id === section)
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length
    setSection(tabs[next].id)
    document.getElementById('approval-tab-' + tabs[next].id)?.focus()
    setPage(0)
  }
  return <>
    <PageHeader eyebrow="Workflow review" title="Approvals and Notifications" description="Explore fictional approval and reminder scenarios. No requests are submitted and no notifications are delivered." />
    <div className="workflow-banner" role="status"><strong>Fictional, partial preview data</strong> - DEMO scenarios only; no live queue or message service is connected.</div>
    <div className="approval-tabs" role="tablist" aria-label="Approval and notification sections">{tabs.map((tab) => <button key={tab.id} id={'approval-tab-' + tab.id} className="approval-tab" type="button" role="tab" aria-selected={section === tab.id} aria-controls={'approval-panel-' + tab.id} tabIndex={section === tab.id ? 0 : -1} onClick={() => { setSection(tab.id); setPage(0) }} onKeyDown={tabKey}>{tab.label}</button>)}</div>
    {preview.loading ? <div className="workflow-message" role="status">Loading approval preview...</div>
      : preview.error ? <div className="workflow-message" role="alert"><strong>Approval and notification preview is unavailable.</strong><p>A local provider could not load. No live data was requested.</p><button type="button" className="button workflow-secondary" onClick={preview.retry}>Try again</button></div>
        : data && section === 'requests' ? <section id="approval-panel-requests" role="tabpanel" aria-labelledby="approval-tab-requests">
          <section className="approval-summary" aria-label="Approval preview summary"><article><span>Illustrative request scenarios</span><strong>{data.preview.requests.length}</strong></article><article><span>Request types represented</span><strong>{new Set(data.preview.requests.map((item) => item.requestType)).size}</strong></article><article><span>Operational decisions recorded</span><strong>Unavailable</strong><small>No decision service is connected</small></article></section>
          <section className="workflow-panel" aria-labelledby="approval-directory-title"><div className="workflow-heading"><div><p className="eyebrow">R-10 preview</p><h2 id="approval-directory-title">Approval request examples</h2></div><span className="workflow-tag">Authority not configured</span></div>
            <p className="approval-notice-state">All rows are illustrative scenarios, not pending requests. The requirements name approval-capable workflows but do not define approvers or stages.</p>
            <div className="approval-toolbar"><label>Search requests<input type="search" aria-label="Search approval requests" value={requestQuery} onChange={(event) => { setRequestQuery(event.target.value); setPage(0) }} placeholder="Reference, type, or related record" /></label><label>Request type<select aria-label="Request type" value={requestType} onChange={(event) => { setRequestType(event.target.value); setPage(0) }}><option value="">All types</option>{requestTypes.map((item) => <option key={item}>{item}</option>)}</select></label><label>Preview state<select aria-label="Request preview state" value={requestState} onChange={(event) => { setRequestState(event.target.value); setPage(0) }}><option value="">All examples</option><option value="example">Illustrative only</option></select></label></div>
            {!visibleRequests.length ? <p className="workflow-message">{data.preview.requests.length ? 'No approval examples match these filters.' : 'No approval examples are available.'}</p> : <div className="workflow-table-wrap"><table className="workflow-table"><caption className="sr-only">Fictional approval request examples</caption><thead><tr><th>Reference</th><th>Request type</th><th>Related preview record</th><th>Example description</th><th>Request date</th><th>Preview state</th><th>Action</th></tr></thead><tbody>{visibleRequests.map((request) => <tr key={request.reference}><td data-label="Reference"><strong>{request.reference}</strong></td><td data-label="Request type">{request.requestType}</td><td data-label="Related preview record">{requestRelated(request, data)}</td><td data-label="Example description">{request.description}</td><td data-label="Request date">{request.requestDate}</td><td data-label="Preview state"><span className="approval-example-badge">Illustrative only</span></td><td data-label="Action"><button className="text-button" type="button" aria-label={'View approval example ' + request.reference} onClick={() => setSelected(request)}>Details</button></td></tr>)}</tbody></table></div>}
            <div className="workflow-pagination"><span>Showing {requests.length ? page * PAGE_SIZE + 1 : 0} - {Math.min((page + 1) * PAGE_SIZE, requests.length)} of {requests.length} - Page {page + 1} of {pages}</span><div><button className="button workflow-secondary" type="button" disabled={page === 0} onClick={() => setPage((value) => value - 1)}>Previous</button><button className="button workflow-secondary" type="button" disabled={page + 1 >= pages} onClick={() => setPage((value) => value + 1)}>Next</button></div></div>
          </section></section>
          : data ? <section id="approval-panel-notifications" role="tabpanel" aria-labelledby="approval-tab-notifications">
            <section className="approval-summary" aria-label="Notification preview summary"><article><span>Illustrative reminder scenarios</span><strong>{data.preview.notifications.length}</strong></article><article><span>Confirmed categories represented</span><strong>{new Set(data.preview.notifications.map((item) => item.category)).size}</strong></article><article><span>Notification delivery</span><strong>Unavailable</strong><small>No messages sent</small></article></section>
            <section className="workflow-panel" aria-labelledby="notification-directory-title"><div className="workflow-heading"><div><p className="eyebrow">R-12 preview</p><h2 id="notification-directory-title">Notification categories</h2></div><span className="workflow-tag">Service not connected</span></div>
              <p className="approval-notice-state">These examples describe requirement categories, not generated or delivered messages. No dates, schedules, escalation, unread counts, or delivery status are inferred.</p>
              <div className="approval-toolbar"><label>Search notifications<input type="search" aria-label="Search notifications" value={notificationQuery} onChange={(event) => { setNotificationQuery(event.target.value); setPage(0) }} placeholder="Title, category or description" /></label><label>Category<select aria-label="Notification category" value={notificationCategory} onChange={(event) => { setNotificationCategory(event.target.value); setPage(0) }}><option value="">All categories</option>{notificationCategories.map((item) => <option key={item}>{item}</option>)}</select></label></div>
              {!visibleNotifications.length ? <p className="workflow-message">{data.preview.notifications.length ? 'No notification examples match these filters.' : 'No notification examples are available.'}</p> : <div className="workflow-table-wrap"><table className="workflow-table"><caption className="sr-only">Fictional notification categories</caption><thead><tr><th>Title</th><th>Category</th><th>Description</th><th>Related preview</th></tr></thead><tbody>{visibleNotifications.map((item) => <tr key={item.reference}><td data-label="Title"><strong>{item.title}</strong><br /><small>{item.reference}</small></td><td data-label="Category">{item.category}</td><td data-label="Description">{item.description}</td><td data-label="Related preview"><NotificationRelated item={item} data={data} openRequest={openRequest} /></td></tr>)}</tbody></table></div>}
              <div className="workflow-pagination"><span>Showing {notifications.length ? page * PAGE_SIZE + 1 : 0} - {Math.min((page + 1) * PAGE_SIZE, notifications.length)} of {notifications.length} - Page {page + 1} of {pages}</span><div><button className="button workflow-secondary" type="button" disabled={page === 0} onClick={() => setPage((value) => value - 1)}>Previous</button><button className="button workflow-secondary" type="button" disabled={page + 1 >= pages} onClick={() => setPage((value) => value + 1)}>Next</button></div></div>
            </section></section> : null}
    {selected && data && <ApprovalDetails request={selected} data={data} close={() => setSelected(null)} />}
  </>
}
