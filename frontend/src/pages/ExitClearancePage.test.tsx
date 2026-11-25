import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { BrowserRouter } from 'react-router-dom'
import App from '../App'
import { mockAssetProvider } from '../assets/mockAssetProvider'
import { navigationItems } from '../components/navigation'
import { mockEmployeeProvider } from '../employees/mockEmployeeProvider'
import { mockWorkflowProvider } from '../workflows/mockWorkflowProvider'
import { mockExitClearanceProvider } from '../exitClearance/mockExitClearanceProvider'
import type { ExitClearancePreviewProvider } from '../exitClearance/types'
import { clearanceCaseSummary } from '../exitClearance/selectors'
import { validateExitClearancePreview } from '../exitClearance/validation'
import { ExitClearancePage } from './ExitClearancePage'
beforeEach(() => { window.history.pushState({}, '', '/exit-clearance') })
function renderPage(props: React.ComponentProps<typeof ExitClearancePage> = {}) { return render(<BrowserRouter><ExitClearancePage {...props} /></BrowserRouter>) }
describe('Employee Exit and Asset Clearance preview', () => {
  it('renders fictional partial cases with reconciled outstanding summary and no backend calls', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
    try {
      renderPage()
      const table = await screen.findByRole('table', { name: 'Fictional employee clearance directory' })
      expect(screen.getByText('Fictional, partial preview data')).toBeInTheDocument()
      expect(within(table).getByText('DEMO-CLEARANCE-001')).toBeInTheDocument()
      const summary = screen.getByRole('region', { name: 'Clearance preview summary' })
      expect(within(summary).getAllByText('6')).toHaveLength(2)
      expect(within(summary).getByText('2')).toBeInTheDocument()
      expect(within(summary).getAllByText('6')).toHaveLength(2)
      expect(screen.getByText(/Not connected. No last synchronization time/)).toBeInTheDocument()
      expect(fetchSpy).not.toHaveBeenCalled()
    } finally { fetchSpy.mockRestore() }
  })
  it('searches, filters and paginates clearance examples', async () => {
    renderPage()
    await screen.findByRole('table', { name: 'Fictional employee clearance directory' })
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(screen.getByText('DEMO-CLEARANCE-006')).toBeInTheDocument()
    fireEvent.change(screen.getByRole('searchbox', { name: 'Search clearance examples' }), { target: { value: 'DEMO-001' } })
    expect(screen.getByText('DEMO-CLEARANCE-001')).toBeInTheDocument()
    fireEvent.change(screen.getByRole('searchbox', { name: 'Search clearance examples' }), { target: { value: '' } })
    fireEvent.change(screen.getByLabelText('Department'), { target: { value: mockEmployeeProvider.departments[0].id } })
    expect(screen.getByText('Showing 1 - 3 of 3 - Page 1 of 1')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Clearance view'), { target: { value: 'outstanding' } })
    expect(screen.getByText('Showing 1 - 1 of 1 - Page 1 of 1')).toBeInTheDocument()
  })
  it('shows outstanding assets and treats recorded returns as unverified for clearance', async () => {
    renderPage()
    await screen.findByRole('table', { name: 'Fictional employee clearance directory' })
    fireEvent.click(screen.getByRole('button', { name: 'View clearance DEMO-CLEARANCE-001' }))
    const outstanding = screen.getByRole('dialog', { name: 'DEMO-CLEARANCE-001' })
    expect(within(outstanding).getByText(/Outstanding tracked assets must be returned/)).toBeInTheDocument()
    expect(within(outstanding).getByText(/Unknown - partial data and verification are not established/)).toBeInTheDocument()
    expect(within(outstanding).getByRole('button', { name: 'Complete inventory clearance (unavailable)' })).toBeDisabled()
    fireEvent.keyDown(document, { key: 'Escape' })
    fireEvent.click(screen.getByRole('button', { name: 'View clearance DEMO-CLEARANCE-003' }))
    const returned = screen.getByRole('dialog', { name: 'DEMO-CLEARANCE-003' })
    expect(within(returned).getByText(/Actual verification is unknown/)).toBeInTheDocument()
    expect(within(returned).getByText(/partial coverage does not establish readiness/)).toBeInTheDocument()
    expect(within(returned).getByRole('link', { name: 'Return preview' })).toHaveAttribute('href', '/returns?allocation=DEMO-ALLOC-003')
  })
  it('keeps employment status separate and validates linked employee and allocation data', async () => {
    const assets = await mockAssetProvider.load()
    const employees = (await mockEmployeeProvider.listEmployees({ offset: 0, limit: 1000 })).items
    const workflow = await mockWorkflowProvider.load()
    const clearance = await mockExitClearanceProvider.load()
    const bundle = { assets, employees, workflow }
    expect(() => validateExitClearancePreview(bundle, clearance)).not.toThrow()
    expect(clearanceCaseSummary(bundle, clearance.cases[0]).outstanding).toHaveLength(1)
    expect(clearanceCaseSummary(bundle, clearance.cases[2]).returns).toHaveLength(1)
    expect(() => validateExitClearancePreview(bundle, { cases: [{ ...clearance.cases[0], employeeId: 'missing' }] })).toThrow()
    renderPage()
    await screen.findByRole('table', { name: 'Fictional employee clearance directory' })
    fireEvent.click(screen.getByRole('button', { name: 'View clearance DEMO-CLEARANCE-004' }))
    const inactive = screen.getByRole('dialog', { name: 'DEMO-CLEARANCE-004' })
    expect(within(inactive).getByText('Inactive')).toBeInTheDocument()
    expect(within(inactive).getByText(/Not connected or independently confirmed/)).toBeInTheDocument()
    expect(within(inactive).queryByText(/departure date/i)).not.toBeInTheDocument()
  })
  it('surfaces loading, empty and failure states without mock fallback', async () => {
    const pending: ExitClearancePreviewProvider = { load: () => new Promise(() => {}) }
    const loading = renderPage({ clearanceProvider: pending })
    expect(screen.getByText('Loading clearance preview...')).toBeInTheDocument()
    loading.unmount()
    const empty: ExitClearancePreviewProvider = { load: async () => ({ cases: [] }) }
    renderPage({ clearanceProvider: empty })
    expect(await screen.findByText('No clearance examples are available.')).toBeInTheDocument()
    const failed: ExitClearancePreviewProvider = { load: async () => { throw new Error('private fixture error') } }
    renderPage({ clearanceProvider: failed })
    expect(await screen.findByRole('alert')).toHaveTextContent('Clearance preview is unavailable.')
    expect(screen.queryByText('private fixture error')).not.toBeInTheDocument()
  })
  it('places the sidebar item after Employees and routes to the preview', async () => {
    expect(navigationItems[navigationItems.findIndex((item) => item.label === 'Exit Clearance') - 1]?.label).toBe('Employees')
    window.history.pushState({}, '', '/dashboard')
    render(<App />)
    fireEvent.click(await screen.findByRole('link', { name: 'Exit Clearance' }))
    expect(await screen.findByRole('heading', { name: 'Exit Clearance' })).toBeInTheDocument()
  })
  it('links Employee details and Dashboard into the clearance preview', async () => {
    const { DashboardPage } = await import('./DashboardPage')
    const dashboard = render(<BrowserRouter><DashboardPage /></BrowserRouter>)
    expect(await screen.findByRole('link', { name: 'Exit clearance preview' })).toHaveAttribute('href', '/exit-clearance')
    dashboard.unmount()
    const { EmployeesPage } = await import('./EmployeesPage')
    render(<BrowserRouter><EmployeesPage /></BrowserRouter>)
    fireEvent.click(await screen.findByRole('button', { name: 'View details for Mira Vale' }))
    expect(screen.getByRole('link', { name: 'View fictional clearance examples' })).toHaveAttribute('href', '/exit-clearance?employee=DEMO-001')
  })
})
