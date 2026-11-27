import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { OperationalTransactionsPage } from './OperationalTransactionsPage'
import type { TransactionApi } from './apiTransactionProvider'

function provider(overrides: Partial<TransactionApi> = {}): TransactionApi {
  return {
    employees: vi.fn().mockResolvedValue([{ id: 'employee-id', employee_number: 'FIC-1', first_name: 'Fictional', last_name: 'User', status: 'active' }]),
    assets: vi.fn().mockResolvedValue([{ id: 'asset-id', asset_number: 'FIC-A1', product_name: 'Fictional device', lifecycle_status: 'available' }]),
    balances: vi.fn().mockResolvedValue([]),
    allocations: vi.fn().mockResolvedValue([]),
    returns: vi.fn().mockResolvedValue([]),
    createAllocation: vi.fn().mockResolvedValue(undefined),
    issueAllocation: vi.fn().mockResolvedValue(undefined),
    decideAllocation: vi.fn().mockResolvedValue(undefined),
    createReturn: vi.fn().mockResolvedValue(undefined),
    decideReturn: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  }
}

describe('OperationalTransactionsPage', () => {
  it('confirms and refreshes only after an API-confirmed allocation request', async () => {
    const api = provider()
    render(<OperationalTransactionsPage api={api} csrfToken="fictional-csrf" />)
    await screen.findByRole('option', { name: /FIC-1/ })
    fireEvent.change(screen.getByLabelText('Active employee'), { target: { value: 'employee-id' } })
    fireEvent.change(screen.getByLabelText('Available asset'), { target: { value: 'asset-id' } })
    fireEvent.click(screen.getByRole('button', { name: 'Submit request' }))
    await waitFor(() => expect(api.createAllocation).toHaveBeenCalledWith({ employee_id: 'employee-id', tracked_asset_id: 'asset-id', quantity: '1' }, 'fictional-csrf'))
    expect(await screen.findByText(/pending explicit approval/)).toBeTruthy()
    expect(api.allocations).toHaveBeenCalledTimes(2)
  })

  it('does not show preview data or a success message after API failure', async () => {
    const api = provider({ employees: vi.fn().mockRejectedValue(new Error('offline')) })
    render(<OperationalTransactionsPage api={api} csrfToken="fictional-csrf" />)
    expect(await screen.findByRole('alert')).toHaveTextContent('No preview data was substituted')
    expect(screen.queryByText('FIC-1')).toBeNull()
  })
})
