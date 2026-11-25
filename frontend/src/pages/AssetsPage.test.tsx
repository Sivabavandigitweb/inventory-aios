import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { mockAssetProvider } from '../assets/mockAssetProvider'
import type { AssetPreviewProvider } from '../assets/types'
import { AssetsPage } from './AssetsPage'

async function ready(provider: AssetPreviewProvider = mockAssetProvider) {
  render(<AssetsPage provider={provider} />)
  return screen.findByRole('table', { name: 'Fictional individual asset directory' })
}
function tab(name: string) { fireEvent.click(screen.getByRole('tab', { name })) }

describe('Assets frontend preview', () => {
  it('renders explicit mock mode and separate individual and quantity summaries without requests', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
    try {
      await ready()
      expect(screen.getByRole('heading', { name: 'Assets' })).toBeInTheDocument()
      expect(screen.getByText('Fictional preview data')).toBeInTheDocument()
      const summary = screen.getByRole('region', { name: 'Asset summary' })
      expect(within(summary).getByText('12')).toBeInTheDocument()
      expect(within(summary).getByText('40')).toBeInTheDocument()
      expect(within(summary).getByText('34')).toBeInTheDocument()
      expect(fetchSpy).not.toHaveBeenCalled()
    } finally { fetchSpy.mockRestore() }
  })

  it('navigates all four sections', async () => {
    await ready()
    tab('Quantity inventory')
    expect(screen.getByRole('table', { name: 'Fictional quantity inventory' })).toBeInTheDocument()
    tab('Product catalog')
    expect(screen.getByRole('table', { name: 'Fictional product catalog' })).toBeInTheDocument()
    tab('Receiving')
    expect(screen.getByText('Illustrative arrivals')).toBeInTheDocument()
    tab('Individual assets')
    expect(screen.getByRole('table', { name: 'Fictional individual asset directory' })).toBeInTheDocument()
  })

  it('supports arrow-key section navigation', async () => {
    await ready()
    const first = screen.getByRole('tab', { name: 'Individual assets' })
    first.focus()
    fireEvent.keyDown(first, { key: 'ArrowRight' })
    expect(screen.getByRole('tab', { name: 'Quantity inventory' })).toHaveFocus()
    expect(screen.getByRole('table', { name: 'Fictional quantity inventory' })).toBeInTheDocument()
    fireEvent.keyDown(screen.getByRole('tab', { name: 'Quantity inventory' }), { key: 'End' })
    expect(screen.getByRole('tab', { name: 'Receiving' })).toHaveFocus()
  })
  it('searches and filters the individual directory', async () => {
    await ready()
    fireEvent.change(screen.getByRole('searchbox', { name: 'Search assets' }), { target: { value: 'DEMO-ASSET-001' } })
    expect(screen.getByText('Showing 1–1 of 1 · Page 1 of 1')).toBeInTheDocument()
    fireEvent.change(screen.getByRole('searchbox', { name: 'Search assets' }), { target: { value: '' } })
    fireEvent.change(screen.getByLabelText('Category'), { target: { value: 'Monitors' } })
    expect(screen.getByText('Showing 1–4 of 4 · Page 1 of 1')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Lifecycle status'), { target: { value: 'Allocated' } })
    expect(screen.getByText('Showing 1–1 of 1 · Page 1 of 1')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Location'), { target: { value: 'Demo North Store' } })
    expect(screen.getByText('No individual assets found. Try another search or filter.')).toBeInTheDocument()
  })

  it('paginates without repeating records', async () => {
    await ready()
    expect(screen.getByText('DEMO-ASSET-001')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(screen.getByText('DEMO-ASSET-006')).toBeInTheDocument()
    expect(screen.queryByText('DEMO-ASSET-001')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Previous' }))
    expect(screen.getByText('DEMO-ASSET-001')).toBeInTheDocument()
  })

  it('opens details and restores focus after Escape', async () => {
    await ready()
    const trigger = screen.getByRole('button', { name: 'View details for DEMO-ASSET-001' })
    trigger.focus()
    fireEvent.click(trigger)
    const dialog = screen.getByRole('dialog', { name: 'DEMO-ASSET-001' })
    expect(within(dialog).getByText(/Allocation, repair, return, transfer and audit history are unavailable/)).toBeInTheDocument()
    expect(within(dialog).getByRole('link', { name: 'View fictional allocation examples' })).toHaveAttribute('href', '/allocations?asset=DEMO-ASSET-001')
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })

  it('uses accessible lifecycle badges, compact condition labels and the shared close style', async () => {
    const table = await ready()
    for (const status of ['Available', 'Allocated', 'Repair', 'Damaged', 'Disposed']) {
      const badge = within(table).getByText(status)
      expect(badge).toHaveClass('asset-status')
      expect(badge).toHaveClass('asset-status-' + status.toLowerCase())
    }
    expect(within(table).getAllByText('Not specified')).toHaveLength(5)
    expect(screen.getByText(/Condition vocabulary is pending approval/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'View details for DEMO-ASSET-001' }))
    const dialog = screen.getByRole('dialog', { name: 'DEMO-ASSET-001' })
    expect(within(dialog).getByRole('button', { name: 'Close panel' })).toHaveClass('asset-close')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Close panel' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
  it('shows internally consistent quantity lots and no stock mutations', async () => {
    await ready()
    tab('Quantity inventory')
    const table = screen.getByRole('table', { name: 'Fictional quantity inventory' })
    expect(within(table).getByText('DEMO-LOT-001')).toBeInTheDocument()
    const row = within(table).getByText('DEMO-LOT-001').closest('tr')
    expect(row).not.toBeNull()
    expect(within(row!).getByText('20')).toBeInTheDocument()
    expect(within(row!).getByText('4')).toBeInTheDocument()
    expect(within(row!).getByText('16')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Adjust stock/ })).not.toBeInTheDocument()
  })

  it('searches products and keeps product creation disabled', async () => {
    await ready()
    tab('Product catalog')
    const table = screen.getByRole('table', { name: 'Fictional product catalog' })
    expect(within(table).getByText('Demo laptop')).toBeInTheDocument()
    fireEvent.change(screen.getByRole('searchbox', { name: 'Search products' }), { target: { value: 'printer' } })
    expect(screen.getByText('Demo printer')).toBeInTheDocument()
    expect(screen.queryByText('Demo laptop')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Add product (unavailable)' })).toBeDisabled()
    expect(screen.getByPlaceholderText('Name, category, SKU, brand or model')).toBeInTheDocument()
  })

  it('shows confirmed receiving fields and disabled submission', async () => {
    await ready()
    tab('Receiving')
    expect(screen.getByText(/Confirmed arrival fields/)).toBeInTheDocument()
    expect(screen.getByText('Identity policy pending')).toBeInTheDocument()
    expect(screen.getByText('Unit and precision pending')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Record receipt (unavailable)' })).toBeDisabled()
    expect(screen.queryByText(/successfully registered/i)).not.toBeInTheDocument()
  })

  it('shows loading, empty and error states without fallback', async () => {
    const pending: AssetPreviewProvider = { load: () => new Promise(() => {}) }
    const loadingView = render(<AssetsPage provider={pending} />)
    expect(screen.getByText('Loading asset preview…')).toBeInTheDocument()
    loadingView.unmount()
    const empty: AssetPreviewProvider = { load: async () => ({ products: [], assets: [], lots: [], receipts: [] }) }
    const emptyView = render(<AssetsPage provider={empty} />)
    expect(await screen.findByText('No individual assets found. Try another search or filter.')).toBeInTheDocument()
    emptyView.unmount()
    const failure: AssetPreviewProvider = { load: async () => { throw new Error('Preview unavailable') } }
    render(<AssetsPage provider={failure} />)
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Asset preview is unavailable.'))
    expect(screen.queryByText('DEMO-ASSET-001')).not.toBeInTheDocument()
  })
})
