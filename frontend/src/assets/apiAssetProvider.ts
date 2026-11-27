import type { AssetPreviewData, AssetPreviewProvider } from './types'

type Page<T> = { items: T[]; total: number; limit: number; offset: number }
type Product = { id: string; name: string; category_name: string; sku: string | null; brand: string | null; model: string | null; specifications: Record<string, unknown>; active: boolean }
type Asset = { id: string; asset_number: string | null; product_id: string; category_name: string; product_name: string; brand: string | null; model: string | null; location_name: string; lifecycle_status: 'available' | 'allocated' | 'repair' | 'damaged' | 'disposed'; condition: string | null }
type Balance = { product_id: string; product_name: string; location_name: string; unit: string; on_hand: string; reserved: string }
type Receipt = { id: string; received_at: string; received_by_id: string; location_id: string; location_name: string; supplier_id: string | null; external_reference: string | null }

async function read<T>(path: string): Promise<T> {
  const response = await fetch(`/api/v1/inventory/${path}`, {
    credentials: 'same-origin', headers: { Accept: 'application/json' },
  })
  if (!response.ok) throw new Error('Inventory service is unavailable.')
  return response.json() as Promise<T>
}

/** API-only provider for authenticated routes. A failed request is always visible. */
export const apiAssetProvider: AssetPreviewProvider = {
  mode: 'authenticated-api',
  async load(): Promise<AssetPreviewData> {
    const [productPage, assetPage, balances, receiptPage] = await Promise.all([
      read<Page<Product>>('products?limit=100&offset=0'),
      read<Page<Asset>>('assets?limit=100&offset=0'),
      read<Balance[]>('quantity-balances'),
      read<Page<Receipt>>('receipts?limit=100&offset=0'),
    ])
    return {
      products: productPage.items.map((product) => ({
        id: product.id, name: product.name, category: product.category_name, sku: product.sku,
        brand: product.brand, model: product.model,
        specifications: Object.entries(product.specifications).map(([key, value]) => `${key}: ${String(value)}`).join(', '),
        active: product.active,
      })),
      assets: assetPage.items.map((asset) => ({
        id: asset.id, identifier: asset.asset_number ?? asset.id, productId: asset.product_id,
        location: asset.location_name, condition: asset.condition ?? 'Not specified',
        status: ({ available: 'Available', allocated: 'Allocated', repair: 'Repair', damaged: 'Damaged', disposed: 'Disposed' } as const)[asset.lifecycle_status],
      })),
      lots: balances.map((balance, index) => ({
        id: `${balance.product_id}-${index}`, reference: 'Balance', productId: balance.product_id,
        location: balance.location_name, physical: Number(balance.on_hand), reserved: Number(balance.reserved), unit: balance.unit,
      })),
      receipts: receiptPage.items.map((receipt) => ({
        id: receipt.id, receivedDate: receipt.received_at.slice(0, 10), receivedBy: `User ${receipt.received_by_id}`,
        quantity: null, location: receipt.location_name, specifications: receipt.external_reference ?? 'Receipt recorded',
      })),
    }
  },
}
