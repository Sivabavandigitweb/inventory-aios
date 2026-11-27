import { describe, expect, it } from 'vitest'
import { mockAssetProvider } from '../assets/mockAssetProvider'
import { mockEmployeeProvider } from '../employees/mockEmployeeProvider'
import { buildDashboardSummary } from './selectors'

describe('dashboard aggregation from shared providers', () => {
  it('reconciles lifecycle, category and location with individual assets', async () => {
    const summary = buildDashboardSummary(await mockAssetProvider.load(), await mockEmployeeProvider.getSummary())
    expect(summary.totalAssets).toBe(12)
    expect(summary.lifecycle).toEqual([
      { label: 'Available', count: 5 },
      { label: 'Allocated', count: 2 },
      { label: 'Repair', count: 2 },
      { label: 'Damaged', count: 2 },
      { label: 'Disposed', count: 1 },
    ])
    expect(summary.lifecycle.reduce((sum, item) => sum + item.count, 0)).toBe(summary.totalAssets)
    expect(summary.categories.reduce((sum, item) => sum + item.count, 0)).toBe(summary.totalAssets)
    expect(summary.locations.reduce((sum, item) => sum + item.count, 0)).toBe(summary.totalAssets)
    expect(summary.employees).toEqual(await mockEmployeeProvider.getSummary())
  })

  it('keeps lot availability separate and computes it per lot', async () => {
    const summary = buildDashboardSummary(await mockAssetProvider.load(), await mockEmployeeProvider.getSummary())
    expect(summary.stock.map((lot) => [lot.physical, lot.reserved, lot.available])).toEqual([
      [20, 4, 16], [12, 2, 10], [8, 0, 8],
    ])
    expect(summary.stock).toHaveLength(3)
    expect(summary.totalAssets).toBe(12)
  })

  it('handles zero assets and zero-quantity lots safely', () => {
    const summary = buildDashboardSummary({
      assets: [], products: [], receipts: [],
      lots: [{ id: 'lot', reference: 'DEMO-ZERO', productId: 'missing', location: 'Demo Store', physical: 0, reserved: 0, unit: 'each' }],
    }, { total: 0, active: 0, inactive: 0, departments: 0 })
    expect(summary.lifecycle.every((item) => item.count === 0)).toBe(true)
    expect(summary.categories).toEqual([])
    expect(summary.locations).toEqual([])
    expect(summary.stock[0].available).toBe(0)
  })
})
