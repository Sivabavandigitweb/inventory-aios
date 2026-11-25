import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { ReportsPage } from './ReportsPage'
import { DashboardPage } from './DashboardPage'

function renderReports(props: Parameters<typeof ReportsPage>[0] = {}) {
  return render(<MemoryRouter><ReportsPage {...props} /></MemoryRouter>)
}
function choose(label: string) { fireEvent.change(screen.getByRole('combobox', { name: 'Report category' }), { target: { value: label } }) }

describe('Reports and Analytics preview', () => {
  it('renders explicit fictional coverage and derives individual asset rows without backend requests', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
    try {
      renderReports()
      expect(screen.getByRole('heading', { name: 'Reports and Analytics' })).toBeInTheDocument()
      expect(screen.getByText(/Fictional, partial preview data/)).toBeInTheDocument()
      expect(await screen.findByRole('table', { name: /Individual asset inventory/ })).toBeInTheDocument()
      expect(screen.getByText('DEMO-ASSET-001')).toBeInTheDocument()
      expect(fetchSpy).not.toHaveBeenCalled()
    } finally { fetchSpy.mockRestore() }
  })

  it('filters the report and keeps total count independent of pagination', async () => {
    renderReports()
    await screen.findByRole('table', { name: /Individual asset inventory/ })
    const summary = screen.getByRole('region', { name: 'Filtered report summary' })
    expect(within(summary).getByText('12')).toBeInTheDocument()
    fireEvent.change(screen.getByRole('searchbox', { name: 'Search report' }), { target: { value: 'DEMO-ASSET-001' } })
    expect(within(summary).getByText('1')).toBeInTheDocument()
    expect(screen.getByText(/1 filtered rows/)).toBeInTheDocument()
  })

  it('shows quantity availability per lot without combining units', async () => {
    renderReports()
    await screen.findByRole('table')
    choose('quantity')
    expect(await screen.findByRole('table', { name: /Quantity inventory/ })).toBeInTheDocument()
    expect(screen.getByText(/Available 16/)).toBeInTheDocument()
    expect(screen.getByText(/units are unapproved/)).toBeInTheDocument()
  })

  it('supports employee and department report categories from shared allocations', async () => {
    renderReports()
    await screen.findByRole('table')
    choose('employee')
    expect(await screen.findAllByText(/fictional allocation records/)).not.toHaveLength(0)
    choose('department')
    expect(await screen.findAllByText('Technology')).not.toHaveLength(0)
  })

  it('provides allocation, return, damage, exit, and approval report previews', async () => {
    renderReports()
    await screen.findByRole('table')
    choose('allocations')
    expect(await screen.findByRole('table', { name: /Allocation report/ })).toBeInTheDocument()
    choose('returns')
    expect(await screen.findByText(/Return rows are historical examples/)).toBeInTheDocument()
    choose('repairs')
    expect(await screen.findByRole('table', { name: /Repair records/ })).toBeInTheDocument()
    choose('damaged')
    expect(await screen.findByText('DEMO-ASSET-011')).toBeInTheDocument()
    choose('exit')
    expect(await screen.findAllByText(/Readiness unknown/)).not.toHaveLength(0)
    choose('approvals')
    expect(await screen.findAllByText(/Illustrative only; no decision recorded/)).not.toHaveLength(0)
  })

  it('distinguishes unavailable purchase, audit, and missing-information reports from empty results', async () => {
    renderReports()
    await screen.findByRole('table')
    for (const [category, message] of [['missing', /No approved completeness rules/], ['purchases', /Purchase dates, supplier, cost, and currency/], ['audit', /Authorized audit history is not connected/]] as const) {
      choose(category)
      expect(await screen.findByRole('heading', { name: /unavailable/ })).toBeInTheDocument()
      expect(screen.getByText(message)).toBeInTheDocument()
    }
  })
  it('keeps export controls disabled and related navigation inside preview routes', async () => {
    renderReports()
    await screen.findByRole('table')
    expect(screen.getByRole('button', { name: 'Export Excel (unavailable)' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Export PDF (unavailable)' })).toBeDisabled()
    expect(screen.getAllByRole('link', { name: 'Open preview' })[0]).toHaveAttribute('href', '/assets?section=assets')
  })

  it('surfaces loading, empty, and provider error states without fallback', async () => {
    const pending = { load: () => new Promise<never>(() => {}) }
    const loading = renderReports({ assetProvider: pending })
    expect(screen.getByText(/Loading report preview/)).toBeInTheDocument()
    loading.unmount()
    const noData = renderReports()
    await screen.findByRole('table')
    fireEvent.change(screen.getByRole('searchbox', { name: 'Search report' }), { target: { value: 'no matching value' } })
    expect(await screen.findByText('No rows match the selected filters.')).toBeInTheDocument()
    noData.unmount()
    const broken = { load: async () => { throw new Error('local failure') } }
    renderReports({ assetProvider: broken })
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Report preview is unavailable'))
    expect(screen.queryByText('DEMO-ASSET-001')).not.toBeInTheDocument()
  })
  it('provides dashboard navigation to the reports preview', async () => {
    render(<MemoryRouter><DashboardPage /></MemoryRouter>)
    expect(await screen.findByRole('link', { name: /Reports preview/ })).toHaveAttribute('href', '/reports')
  })

})
