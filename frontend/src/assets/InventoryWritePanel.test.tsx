import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { InventoryWritePanel } from './InventoryWritePanel'
import type { InventoryWriteProvider } from './apiInventoryWriteProvider'

function provider(overrides: Partial<InventoryWriteProvider> = {}): InventoryWriteProvider {
  return {
    loadCategories: vi.fn().mockResolvedValue([{ id: 'category-1', code: 'DEMO', name: 'Demo category', tracking_mode: 'individual' }]),
    loadLocations: vi.fn().mockResolvedValue([{ id: 'location-1', code: 'DEMO', name: 'Demo location' }]),
    loadProducts: vi.fn().mockResolvedValue([{ id: 'product-1', category_id: 'category-1', name: 'Demo product', active: true }]),
    loadCandidates: vi.fn().mockResolvedValue([]),
    loadApprovals: vi.fn().mockResolvedValue([]),
    loadFinalizations: vi.fn().mockResolvedValue([]),
    createProduct: vi.fn().mockResolvedValue({ id: 'new-product', status: 'pending_approval', replayed: false }),
    createReceipt: vi.fn().mockResolvedValue({ id: 'new-receipt', status: 'pending_approval', replayed: false }),
    submitAssetRegistration: vi.fn().mockResolvedValue({ id: 'new-request', status: 'pending_approval', replayed: false }),
    submitQuantityRegistration: vi.fn().mockResolvedValue({ id: 'new-request', status: 'pending_approval', replayed: false }),
    decideApproval: vi.fn().mockResolvedValue(undefined),
    finalizeRegistration: vi.fn().mockResolvedValue({ id: 'new-lot', status: 'registered', replayed: false }),
    ...overrides,
  }
}

describe('authenticated inventory write panel', () => {
  it('submits a product only through the API and refreshes after confirmed success', async () => {
    const api = provider()
    const onConfirmed = vi.fn()
    render(<InventoryWritePanel provider={api} csrfToken="fictional-csrf" onConfirmed={onConfirmed} />)
    await screen.findByRole('heading', { name: 'New product' })
    fireEvent.change(screen.getByLabelText('Category'), { target: { value: 'category-1' } })
    fireEvent.change(screen.getByLabelText('Product name'), { target: { value: 'Fictional product' } })
    fireEvent.click(screen.getByRole('button', { name: 'Submit product' }))
    expect(await screen.findByRole('status')).toHaveTextContent('Product request confirmed: pending_approval.')
    expect(api.createProduct).toHaveBeenCalledWith(expect.objectContaining({ category_id: 'category-1', name: 'Fictional product' }), 'fictional-csrf')
    await waitFor(() => expect(onConfirmed).toHaveBeenCalledTimes(1))
  })

  it('does not report success or refresh when the API fails', async () => {
    const api = provider({ createProduct: vi.fn().mockRejectedValue(new Error('offline')) })
    const onConfirmed = vi.fn()
    render(<InventoryWritePanel provider={api} csrfToken="fictional-csrf" onConfirmed={onConfirmed} />)
    await screen.findByRole('heading', { name: 'New product' })
    fireEvent.change(screen.getByLabelText('Category'), { target: { value: 'category-1' } })
    fireEvent.change(screen.getByLabelText('Product name'), { target: { value: 'Fictional product' } })
    fireEvent.click(screen.getByRole('button', { name: 'Submit product' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('The request was not confirmed.')
    expect(onConfirmed).not.toHaveBeenCalled()
  })

  it('requires CSRF evidence before displaying enabled mutation controls', async () => {
    const api = provider()
    render(<InventoryWritePanel provider={api} csrfToken="" onConfirmed={vi.fn()} />)
    expect(await screen.findByRole('button', { name: 'Submit product' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Submit receipt' })).toBeDisabled()
  })

  it('submits a registration approval decision through the API and refreshes', async () => {
    const item = { id: 'approval-id', entity_type: 'asset_registration', entity_id: 'request-id', required_capability: 'approvals:decide:asset_registration', requested_by_id: 'requester-id', created_at: '2026-11-27T08:00:00Z' }
    const api = provider({ loadApprovals: vi.fn().mockResolvedValue([item]) })
    const onConfirmed = vi.fn()
    render(<InventoryWritePanel provider={api} csrfToken="fictional-csrf" onConfirmed={onConfirmed} />)
    await screen.findByText('asset registration')
    fireEvent.click(screen.getByRole('button', { name: 'Approve' }))
    await waitFor(() => expect(api.decideApproval).toHaveBeenCalledWith('approval-id', 'approved', 'fictional-csrf'))
    await waitFor(() => expect(onConfirmed).toHaveBeenCalledTimes(1))
  })
})
