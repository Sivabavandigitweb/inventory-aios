import { describe, expect, it } from 'vitest'
import { mockAssetProvider } from './mockAssetProvider'

describe('fictional asset provider', () => {
  it('returns linked fictional products, assets, lots and receipt previews', async () => {
    const data = await mockAssetProvider.load()
    const productIds = new Set(data.products.map(({ id }) => id))
    expect(data.assets.every(({ productId }) => productIds.has(productId))).toBe(true)
    expect(data.lots.every(({ productId }) => productIds.has(productId))).toBe(true)
    expect(data.assets.every(({ identifier }) => identifier.startsWith('DEMO-ASSET-'))).toBe(true)
    expect(data.lots.every(({ physical, reserved }) => physical >= reserved && reserved >= 0)).toBe(true)
    expect(new Set(data.assets.map(({ status }) => status))).toEqual(
      new Set(['Available', 'Allocated', 'Repair', 'Damaged', 'Disposed']),
    )
  })
})