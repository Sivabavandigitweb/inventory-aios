import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { BrowserRouter } from 'react-router-dom'
import { mockAssetProvider } from '../assets/mockAssetProvider'
import { mockEmployeeProvider } from '../employees/mockEmployeeProvider'
import { mockWorkflowProvider } from '../workflows/mockWorkflowProvider'
import { mockApprovalNotificationProvider } from '../approvals/mockApprovalNotificationProvider'
import type { ApprovalNotificationPreviewProvider } from '../approvals/types'
import { validateApprovalPreview } from '../approvals/validation'
import { ApprovalsPage } from './ApprovalsPage'
beforeEach(() => { window.history.pushState({}, '', '/approvals') })
function renderPage(props: React.ComponentProps<typeof ApprovalsPage> = {}) { return render(<BrowserRouter><ApprovalsPage {...props} /></BrowserRouter>) }
describe('Approvals and Notifications preview', () => {
  it('renders fictional approval examples with reconciled summary and no backend calls', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
    try {
      renderPage()
      const table = await screen.findByRole('table', { name: 'Fictional approval request examples' })
      expect(screen.getByText('Fictional, partial preview data')).toBeInTheDocument()
      expect(within(table).getByText('DEMO-APPROVAL-001')).toBeInTheDocument()
      const summary = screen.getByRole('region', { name: 'Approval preview summary' })
      expect(within(summary).getAllByText('4')[0]).toBeInTheDocument()
      expect(within(summary).getByText('Unavailable')).toBeInTheDocument()
      expect(fetchSpy).not.toHaveBeenCalled()
    } finally { fetchSpy.mockRestore() }
  })
  it('navigates accessible sections and shows confirmed notification categories without delivery', async () => {
    renderPage()
    await screen.findByRole('table', { name: 'Fictional approval request examples' })
    const requestsTab = screen.getByRole('tab', { name: 'Approval requests' })
    requestsTab.focus()
    fireEvent.keyDown(requestsTab, { key: 'ArrowRight' })
    const notices = await screen.findByRole('table', { name: 'Fictional notification categories' })
    expect(screen.getByRole('tab', { name: 'Notifications' })).toHaveAttribute('aria-selected', 'true')
    expect(within(notices).getByText('Warranty expiration')).toBeInTheDocument()
    expect(within(notices).getAllByRole('row')).toHaveLength(4)
    expect(screen.getByText(/No dates, schedules, escalation, unread counts/)).toBeInTheDocument()
  })
  it('searches, filters and paginates approval examples', async () => {
    renderPage()
    await screen.findByRole('table', { name: 'Fictional approval request examples' })
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(screen.getByText('DEMO-APPROVAL-004')).toBeInTheDocument()
    fireEvent.change(screen.getByRole('searchbox', { name: 'Search approval requests' }), { target: { value: 'DEMO-APPROVAL-002' } })
    expect(screen.getByText('DEMO-APPROVAL-002')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Request type'), { target: { value: 'Allocation' } })
    expect(screen.getByText('Showing 1 - 1 of 1 - Page 1 of 1')).toBeInTheDocument()
    expect(screen.queryByText('DEMO-APPROVAL-003')).not.toBeInTheDocument()
  })
  it('shows request details and keeps decisions disabled', async () => {
    renderPage()
    await screen.findByRole('table', { name: 'Fictional approval request examples' })
    fireEvent.click(screen.getByRole('button', { name: 'View approval example DEMO-APPROVAL-003' }))
    const dialog = screen.getByRole('dialog', { name: 'DEMO-APPROVAL-003' })
    expect(within(dialog).getByText('Return')).toBeInTheDocument()
    expect(within(dialog).getByText(/Approver authority is not configured/)).toBeInTheDocument()
    expect(within(dialog).getByRole('button', { name: 'Approve (unavailable)' })).toBeDisabled()
    expect(within(dialog).getByRole('button', { name: 'Reject (unavailable)' })).toBeDisabled()
    expect(within(dialog).getByRole('link', { name: 'Open allocation preview' })).toHaveAttribute('href', '/allocations?asset=DEMO-ASSET-002')
  })
  it('filters notification examples and opens related approval preview without sending anything', async () => {
    renderPage()
    await screen.findByRole('table', { name: 'Fictional approval request examples' })
    fireEvent.click(screen.getByRole('tab', { name: 'Notifications' }))
    const table = await screen.findByRole('table', { name: 'Fictional notification categories' })
    expect(within(table).getByText('DEMO-NOTICE-001')).toBeInTheDocument()
    fireEvent.change(screen.getByRole('searchbox', { name: 'Search notifications' }), { target: { value: 'warranty' } })
    expect(screen.getByText('Warranty expiration reminder category')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Search notifications'), { target: { value: '' } })
    fireEvent.change(screen.getByLabelText('Notification category'), { target: { value: 'Pending approvals' } })
    fireEvent.click(screen.getByRole('button', { name: 'View approval example' }))
    expect(screen.getByRole('dialog', { name: 'DEMO-APPROVAL-001' })).toBeInTheDocument()
  })
  it('validates request, notification, asset, employee, receipt and allocation references', async () => {
    const assets = await mockAssetProvider.load()
    const employees = (await mockEmployeeProvider.listEmployees({ offset: 0, limit: 1000 })).items
    const workflow = await mockWorkflowProvider.load()
    const bundle = { assets, employees, workflow }
    const data = await mockApprovalNotificationProvider.load()
    expect(() => validateApprovalPreview(bundle, data)).not.toThrow()
    expect(() => validateApprovalPreview(bundle, { ...data, requests: [{ ...data.requests[0], receiptId: 'missing' }] })).toThrow()
    expect(() => validateApprovalPreview(bundle, { ...data, notifications: [{ ...data.notifications[0], approvalReference: 'missing' }] })).toThrow()
  })
  it('surfaces loading, empty and error states without substituting fixture data', async () => {
    const pending: ApprovalNotificationPreviewProvider = { load: () => new Promise(() => {}) }
    const loading = renderPage({ approvalProvider: pending })
    expect(screen.getByText('Loading approval preview...')).toBeInTheDocument()
    loading.unmount()
    const empty: ApprovalNotificationPreviewProvider = { load: async () => ({ requests: [], notifications: [] }) }
    renderPage({ approvalProvider: empty })
    expect(await screen.findByText('No approval examples are available.')).toBeInTheDocument()
    const failed: ApprovalNotificationPreviewProvider = { load: async () => { throw new Error('private provider message') } }
    renderPage({ approvalProvider: failed })
    expect(await screen.findByRole('alert')).toHaveTextContent('Approval and notification preview is unavailable.')
    expect(screen.queryByText('private provider message')).not.toBeInTheDocument()
  })
  it('links the dashboard to approvals', async () => {
    const { DashboardPage } = await import('./DashboardPage')
    render(<BrowserRouter><DashboardPage /></BrowserRouter>)
    expect(await screen.findByRole('link', { name: 'Approvals preview' })).toHaveAttribute('href', '/approvals')
  })
})
