import { render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import type { AssetPreviewProvider } from '../assets/types'
import { mockEmployeeProvider } from '../employees/mockEmployeeProvider'
import type { EmployeeDirectoryProvider } from '../employees/types'
import { DashboardPage } from './DashboardPage'

function show(assetProvider?: AssetPreviewProvider, employeeProvider?: EmployeeDirectoryProvider) {
  return render(<MemoryRouter><DashboardPage assetProvider={assetProvider} employeeProvider={employeeProvider} /></MemoryRouter>)
}

describe('Inventory dashboard preview', () => {
  it('renders fictional mode, summaries and accessible distribution lists without backend requests', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
    try {
      show()
      expect(screen.getByRole('heading', { name: 'Inventory dashboard' })).toBeInTheDocument()
      expect(screen.getByText('Fictional preview data')).toBeInTheDocument()
      const summary = await screen.findByRole('region', { name: 'Inventory summary' })
      await waitFor(() => expect(within(summary).getAllByText('12')).toHaveLength(2))
      expect(within(summary).getByText('5')).toBeInTheDocument()
      expect(within(summary).getByText('2')).toBeInTheDocument()
      const lifecycle = screen.getByRole('list', { name: 'lifecycle distribution' })
      expect(within(lifecycle).getAllByRole('listitem')).toHaveLength(5)
      expect(fetchSpy).not.toHaveBeenCalled()
    } finally { fetchSpy.mockRestore() }
  })

  it('shows category and location counts and per-lot stock availability', async () => {
    show()
    await screen.findByRole('list', { name: 'category distribution' })
    const categories = screen.getByRole('list', { name: 'category distribution' })
    expect(within(categories).getAllByRole('listitem')).toHaveLength(3)
    expect(within(categories).getByText('Laptops')).toBeInTheDocument()
    const locations = screen.getByRole('list', { name: 'location distribution' })
    expect(within(locations).getAllByRole('listitem')).toHaveLength(2)
    const stock = screen.getByRole('list', { name: 'Stock availability by lot' })
    expect(within(stock).getByText('16 available')).toBeInTheDocument()
    expect(within(stock).getByText('10 available')).toBeInTheDocument()
    expect(within(stock).getByText('8 available')).toBeInTheDocument()
    expect(screen.getByText(/different products are not totaled together/)).toBeInTheDocument()
  })

  it('matches the employee directory summary and marks synchronization unavailable', async () => {
    show()
    const people = await screen.findByRole('region', { name: 'Employee overview' })
    const expected = await mockEmployeeProvider.getSummary()
    await waitFor(() => expect(within(people).getByText(String(expected.total))).toBeInTheDocument())
    expect(within(people).getByText(String(expected.active))).toBeInTheDocument()
    expect(within(people).getAllByText(String(expected.inactive))).toHaveLength(2)
    const sync = screen.getByRole('region', { name: 'Employee synchronization' })
    expect(within(sync).getByText('Not connected')).toBeInTheDocument()
    expect(within(sync).getByText('Not available')).toBeInTheDocument()
  })

  it('provides working route targets and labels unavailable operations without fake counts', async () => {
    show()
    await screen.findByRole('region', { name: 'Inventory summary' })
    const nav = screen.getByRole('navigation', { name: 'Quick navigation' })
    expect(within(nav).getByRole('link', { name: /Asset directory/ })).toHaveAttribute('href', '/assets?section=assets')
    expect(within(nav).getByRole('link', { name: /Quantity inventory/ })).toHaveAttribute('href', '/assets?section=quantity')
    expect(within(nav).getByRole('link', { name: /Product catalog/ })).toHaveAttribute('href', '/assets?section=products')
    expect(within(nav).getByRole('link', { name: /Employee directory/ })).toHaveAttribute('href', '/employees')
    const operations = screen.getByRole('region', { name: 'Operational activity and pending actions' })
    expect(within(operations).getByText('Pending approvals — unavailable')).toBeInTheDocument()
    expect(within(operations).getByText('Overdue returns — unavailable')).toBeInTheDocument()
    expect(within(operations).getByText('Active repair workflows — unavailable')).toBeInTheDocument()
    expect(within(operations).getByText('Recent inventory transactions — unavailable')).toBeInTheDocument()
    expect(within(operations).getByText('Employee exit clearance — unavailable')).toBeInTheDocument()
  })

  it('shows loading, empty and error states without fallback', async () => {
    const pending: AssetPreviewProvider = { load: () => new Promise(() => {}) }
    const loading = show(pending)
    expect(screen.getByText('Loading dashboard preview…')).toBeInTheDocument()
    loading.unmount()
    const empty: AssetPreviewProvider = { load: async () => ({ assets: [], products: [], lots: [], receipts: [] }) }
    const noData = show(empty)
    expect(await screen.findAllByText('No individual assets in this preview.')).toHaveLength(3)
    expect(screen.getByText('No quantity stock in this preview.')).toBeInTheDocument()
    noData.unmount()
    const failure: AssetPreviewProvider = { load: async () => { throw new Error('local preview failed') } }
    show(failure)
    expect(await screen.findByRole('alert')).toHaveTextContent('Dashboard preview is unavailable.')
    expect(screen.queryByRole('region', { name: 'Inventory summary' })).not.toBeInTheDocument()
  })

  it('does not substitute asset mock records when the employee provider fails', async () => {
    const failed: EmployeeDirectoryProvider = {
      ...mockEmployeeProvider, getSummary: async () => { throw new Error('local preview failed') },
    }
    show(undefined, failed)
    expect(await screen.findByRole('alert')).toHaveTextContent('Dashboard preview is unavailable.')
  })
})
