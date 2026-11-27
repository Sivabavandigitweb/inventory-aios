import { afterEach, describe, expect, it, vi } from 'vitest'
import { apiEmployeeProvider } from './apiEmployeeProvider'

describe('authenticated employee API provider', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('loads only through the protected API with same-origin credentials', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ items: [], total: 0, limit: 5, offset: 0 }) })
    vi.stubGlobal('fetch', fetchMock)
    await apiEmployeeProvider.listEmployees({ limit: 5, offset: 0 })
    expect(fetchMock.mock.calls[0][0]).toContain('/api/v1/employees?')
    expect(fetchMock.mock.calls[0][1].credentials).toBe('same-origin')
  })

  it('does not replace API errors with fictional employees', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false }))
    await expect(apiEmployeeProvider.getSummary()).rejects.toThrow('Employee service is unavailable.')
  })
})
