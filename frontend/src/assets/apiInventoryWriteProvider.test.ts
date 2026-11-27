import { afterEach, describe, expect, it, vi } from 'vitest'
import { apiInventoryWriteProvider } from './apiInventoryWriteProvider'

describe('authenticated inventory write API provider', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('sends same-origin credentials, CSRF evidence, and idempotency keys', async () => {
    vi.stubGlobal('crypto', { randomUUID: () => 'fictional-idempotency-key' })
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 201, json: async () => ({ id: 'fictional-id', status: 'pending_approval', replayed: false }) })
    vi.stubGlobal('fetch', fetchMock)
    await apiInventoryWriteProvider.createProduct({ category_id: 'fictional-category', name: 'Keyboard' }, 'fictional-csrf')
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/inventory/products', expect.objectContaining({
      method: 'POST', credentials: 'same-origin', cache: 'no-store',
      headers: expect.objectContaining({
        'X-CSRF-Token': 'fictional-csrf', 'Idempotency-Key': 'fictional-idempotency-key',
      }),
    }))
  })

  it('refuses to send state changes without CSRF evidence', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    await expect(apiInventoryWriteProvider.createProduct({ category_id: 'fictional-category', name: 'Keyboard' }, ''))
      .rejects.toThrow('A verified session is required.')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('does not treat a failed response as a successful inventory mutation', async () => {
    vi.stubGlobal('crypto', { randomUUID: () => 'fictional-idempotency-key' })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 503 }))
    await expect(apiInventoryWriteProvider.createReceipt({
      received_at: '2026-11-26T00:00:00Z', location_id: 'fictional-location', lines: [],
    }, 'fictional-csrf')).rejects.toThrow('The inventory operation could not be confirmed.')
  })

  it('loads only the scoped registration candidates and pending approvals', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => [] })
      .mockResolvedValueOnce({ ok: true, json: async () => [] })
      .mockResolvedValueOnce({ ok: true, json: async () => [] })
    vi.stubGlobal('fetch', fetchMock)
    await apiInventoryWriteProvider.loadCandidates('individual')
    await apiInventoryWriteProvider.loadApprovals()
    expect(fetchMock.mock.calls.map(([url]) => String(url))).toEqual([
      '/api/v1/inventory/registration-candidates?tracking_mode=individual',
      '/api/v1/inventory/registration-approvals',
    ])
  })
})
