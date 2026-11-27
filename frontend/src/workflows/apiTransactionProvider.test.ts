import { afterEach, describe, expect, it, vi } from 'vitest'
import { apiTransactionProvider } from './apiTransactionProvider'

afterEach(() => vi.restoreAllMocks())

describe('apiTransactionProvider', () => {
  it('sends authenticated allocation requests with CSRF and idempotency controls', async () => {
    vi.stubGlobal('crypto', { randomUUID: () => 'fictional-idempotency-key' })
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 201 })
    vi.stubGlobal('fetch', fetchMock)
    await apiTransactionProvider.createAllocation({ employee_id: 'fictional-employee' }, 'fictional-csrf')
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/inventory/allocations', expect.objectContaining({
      credentials: 'same-origin',
      headers: expect.objectContaining({ 'X-CSRF-Token': 'fictional-csrf', 'Idempotency-Key': 'fictional-idempotency-key' }),
    }))
  })

  it('does not submit a write without CSRF evidence', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    await expect(apiTransactionProvider.createReturn({ allocation_line_id: 'fictional-line', quantity: '1', condition: 'good' }, '')).rejects.toThrow('verified session')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('does not treat an unconfirmed backend response as success', async () => {
    vi.stubGlobal('crypto', { randomUUID: () => 'fictional-idempotency-key' })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 503 }))
    await expect(apiTransactionProvider.decideAllocation('fictional-allocation', 'approved', 'fictional-csrf')).rejects.toThrow('could not be confirmed')
  })

  it('loads operational history without substituting preview content', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => [] })
    vi.stubGlobal('fetch', fetchMock)
    await apiTransactionProvider.allocations()
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/inventory/allocations', expect.objectContaining({ cache: 'no-store', credentials: 'same-origin' }))
  })
})
