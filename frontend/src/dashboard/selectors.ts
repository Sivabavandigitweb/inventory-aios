import type { AssetPreviewData, AssetStatus } from '../assets/types'
import type { EmployeeSummary } from '../employees/types'

export const LIFECYCLE_STATUSES: AssetStatus[] = ['Available', 'Allocated', 'Repair', 'Damaged', 'Disposed']

export type CountItem = { label: string; count: number }
export type StockItem = {
  reference: string
  product: string
  location: string
  physical: number
  reserved: number
  available: number
}
export type DashboardSummary = {
  totalAssets: number
  lifecycle: CountItem[]
  categories: CountItem[]
  locations: CountItem[]
  stock: StockItem[]
  employees: EmployeeSummary
}

function countBy(values: string[]): CountItem[] {
  const counts = new Map<string, number>()
  for (const value of values) counts.set(value, (counts.get(value) ?? 0) + 1)
  return [...counts].map(([label, count]) => ({ label, count }))
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label))
}

/** All asset distributions refer to individual units. Lots remain separate. */
export function buildDashboardSummary(data: AssetPreviewData, employees: EmployeeSummary): DashboardSummary {
  const products = new Map(data.products.map((product) => [product.id, product]))
  return {
    totalAssets: data.assets.length,
    lifecycle: LIFECYCLE_STATUSES.map((status) => ({
      label: status, count: data.assets.filter((asset) => asset.status === status).length,
    })),
    categories: countBy(data.assets.map((asset) => products.get(asset.productId)?.category ?? 'Unmapped preview product')),
    locations: countBy(data.assets.map((asset) => asset.location)),
    stock: data.lots.map((lot) => ({
      reference: lot.reference,
      product: products.get(lot.productId)?.name ?? 'Unmapped preview product',
      location: lot.location,
      physical: lot.physical,
      reserved: lot.reserved,
      available: lot.physical - lot.reserved,
    })),
    employees,
  }
}
