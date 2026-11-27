import { afterEach, describe, expect, it, vi } from 'vitest'
import { apiAssetProvider } from './apiAssetProvider'

describe('authenticated asset API provider', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('uses same-origin credentials for protected inventory reads', async () => {
    const page = { items: [], total: 0, limit: 100, offset: 0 }
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => page })
      .mockResolvedValueOnce({ ok: true, json: async () => page })
      .mockResolvedValueOnce({ ok: true, json: async () => [] })
      .mockResolvedValueOnce({ ok: true, json: async () => page })
    vi.stubGlobal('fetch', fetchMock)
    await apiAssetProvider.load()
    expect(fetchMock).toHaveBeenCalledTimes(4)
    expect(fetchMock.mock.calls.every(([url, init]) => String(url).startsWith('/api/v1/inventory/')
      && init?.credentials === 'same-origin')).toBe(true)
  })

  it('surfaces service failure and does not substitute preview data', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false }))
    await expect(apiAssetProvider.load()).rejects.toThrow('Inventory service is unavailable.')
  })
})
