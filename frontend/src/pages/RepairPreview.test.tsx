import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { BrowserRouter } from 'react-router-dom'
import { mockAssetProvider } from '../assets/mockAssetProvider'
import { mockEmployeeProvider } from '../employees/mockEmployeeProvider'
import { mockWorkflowProvider } from '../workflows/mockWorkflowProvider'
import { mockRepairProvider } from '../repairs/mockRepairProvider'
import type { RepairPreviewProvider } from '../repairs/types'
import { validateRepairPreview } from '../repairs/validation'
import { RepairsPage } from './RepairsPage'
function renderRepairs(props: React.ComponentProps<typeof RepairsPage> = {}) { return render(<BrowserRouter><RepairsPage {...props} /></BrowserRouter>) }
describe('Repair Management preview', () => {
  it('renders fictional partial examples, reconciled summaries, and makes no backend request', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
    try {
      renderRepairs()
      const table = await screen.findByRole('table', { name: 'Fictional repair directory' })
      expect(screen.getByText('Fictional, partial preview data')).toBeInTheDocument()
      expect(within(table).getByText('DEMO-REPAIR-001')).toBeInTheDocument()
      const summary = screen.getByRole('region', { name: 'Repair preview summary' })
      expect(within(summary).getByText('6')).toBeInTheDocument()
      expect(within(summary).getByText('2')).toBeInTheDocument()
      expect(within(summary).getByText('4')).toBeInTheDocument()
      expect(fetchSpy).not.toHaveBeenCalled()
    } finally { fetchSpy.mockRestore() }
  })
  it('searches, filters and paginates fictional repair examples', async () => {
    renderRepairs()
    await screen.findByRole('table', { name: 'Fictional repair directory' })
    expect(screen.getByText('DEMO-REPAIR-001')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(screen.getByText('DEMO-REPAIR-006')).toBeInTheDocument()
    fireEvent.change(screen.getByRole('searchbox', { name: 'Search repairs' }), { target: { value: 'DEMO-ASSET-004' } })
    expect(screen.getByText('DEMO-REPAIR-001')).toBeInTheDocument()
    fireEvent.change(screen.getByRole('searchbox', { name: 'Search repairs' }), { target: { value: '' } })
    fireEvent.change(screen.getByLabelText('Preview grouping'), { target: { value: 'Open example' } })
    expect(screen.getByText('Showing 1-2 of 2 - Page 1 of 1')).toBeInTheDocument()
    expect(screen.queryByText('DEMO-REPAIR-003')).not.toBeInTheDocument()
  })
  it('opens details with unavailable outcome and does not mutate lifecycle', async () => {
    renderRepairs()
    await screen.findByRole('table', { name: 'Fictional repair directory' })
    fireEvent.click(screen.getByRole('button', { name: 'View repair DEMO-REPAIR-001' }))
    const dialog = screen.getByRole('dialog', { name: 'DEMO-REPAIR-001' })
    expect(within(dialog).getByText('Damaged')).toBeInTheDocument()
    expect(within(dialog).getByText(/No repair outcome or verification is recorded/)).toBeInTheDocument()
    expect(within(dialog).getByText(/Costs, supporting documents, completion evidence/)).toBeInTheDocument()
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
  it('allows fictional asset selection but keeps repair submission disabled', async () => {
    renderRepairs()
    await screen.findByRole('table', { name: 'Fictional repair directory' })
    fireEvent.click(screen.getByRole('button', { name: 'New Repair preview' }))
    const dialog = screen.getByRole('dialog', { name: 'New Repair preview' })
    fireEvent.change(within(dialog).getByRole('searchbox', { name: 'Search assets for repair' }), { target: { value: 'DEMO-ASSET-004' } })
    fireEvent.change(within(dialog).getByLabelText('Select fictional asset'), { target: { value: 'asset-4' } })
    expect(within(dialog).getByText(/Selection is not eligibility approval/)).toBeInTheDocument()
    expect(within(dialog).getByRole('button', { name: 'Submit repair (unavailable)' })).toBeDisabled()
    expect(within(dialog).getByText(/Reporter identity comes from future authenticated context/)).toBeInTheDocument()
  })
  it('validates references, open status and current custody consistency', async () => {
    const assets = await mockAssetProvider.load()
    const employees = (await mockEmployeeProvider.listEmployees({ offset: 0, limit: 1000 })).items
    const workflow = await mockWorkflowProvider.load()
    const bundle = { assets, employees, workflow }
    const repairs = await mockRepairProvider.load()
    expect(() => validateRepairPreview(bundle, repairs)).not.toThrow()
    expect(() => validateRepairPreview(bundle, { repairs: [{ ...repairs.repairs[0], assetId: 'missing' }] })).toThrow()
    expect(() => validateRepairPreview(bundle, { repairs: [{ ...repairs.repairs[0], assetId: 'asset-2' }] })).toThrow()
  })
  it('surfaces loading, empty and provider errors without substituting mock data', async () => {
    const pending: RepairPreviewProvider = { load: () => new Promise(() => {}) }
    const loading = renderRepairs({ repairProvider: pending })
    expect(screen.getByText('Loading repair preview...')).toBeInTheDocument()
    loading.unmount()
    const empty: RepairPreviewProvider = { load: async () => ({ repairs: [] }) }
    renderRepairs({ repairProvider: empty })
    expect(await screen.findByText('No repair examples are available.')).toBeInTheDocument()
    const failed: RepairPreviewProvider = { load: async () => { throw new Error('private provider detail') } }
    renderRepairs({ repairProvider: failed })
    expect(await screen.findByRole('alert')).toHaveTextContent('Repair preview is unavailable.')
    expect(screen.queryByText('private provider detail')).not.toBeInTheDocument()
  })
  it('exposes repair navigation from dashboard and asset details', async () => {
    const { DashboardPage } = await import('./DashboardPage')
    const { AssetsPage } = await import('./AssetsPage')
    const dashboard = render(<BrowserRouter><DashboardPage /></BrowserRouter>)
    const dashboardLink = await screen.findByRole('link', { name: 'Repairs preview' })
    expect(dashboardLink).toHaveAttribute('href', '/repairs')
    dashboard.unmount()
    render(<BrowserRouter><AssetsPage /></BrowserRouter>)
    await screen.findByRole('table', { name: 'Fictional individual asset directory' })
    fireEvent.click(screen.getByRole('button', { name: 'View details for DEMO-ASSET-004' }))
    expect(screen.getByRole('link', { name: 'View fictional repair examples' })).toHaveAttribute('href', '/repairs?asset=DEMO-ASSET-004')
  })

})
