import type { AssetPreviewData, AssetPreviewProvider, PreviewAsset } from './types'

const products: AssetPreviewData['products'] = [
  { id: 'p1', name: 'Demo laptop', category: 'Laptops', sku: 'DEMO-SKU-LAP', brand: 'Example', model: 'Model A', specifications: 'Illustrative 16 GB memory', active: true },
  { id: 'p2', name: 'Demo monitor', category: 'Monitors', sku: null, brand: 'Example', model: 'Model B', specifications: 'Illustrative 24-inch display', active: true },
  { id: 'p3', name: 'Demo chair', category: 'Furniture', sku: null, brand: null, model: null, specifications: 'Illustrative office chair', active: true },
  { id: 'p4', name: 'Demo network cable', category: 'Computer Accessories', sku: 'DEMO-SKU-CAB', brand: null, model: null, specifications: 'Illustrative cable', active: true },
  { id: 'p5', name: 'Demo adapter', category: 'Computer Accessories', sku: null, brand: 'Example', model: 'Model C', specifications: 'Illustrative adapter', active: true },
  { id: 'p6', name: 'Demo printer', category: 'Printers', sku: null, brand: 'Example', model: 'Model D', specifications: 'Illustrative printer', active: false },
]
const statuses: PreviewAsset['status'][] = [
  'Available', 'Allocated', 'Repair', 'Damaged', 'Disposed',
  'Available', 'Allocated', 'Available', 'Repair', 'Available',
  'Damaged', 'Available',
]
const assets: PreviewAsset[] = statuses.map((status, index) => ({
  id: 'asset-' + String(index + 1),
  identifier: 'DEMO-ASSET-' + String(index + 1).padStart(3, '0'),
  productId: ['p1', 'p2', 'p3'][index % 3],
  location: index % 2 === 0 ? 'Demo North Store' : 'Demo South Store',
  condition: 'Preview description; condition vocabulary pending',
  status,
}))
const data: AssetPreviewData = {
  products,
  assets,
  lots: [
    { id: 'lot-1', reference: 'DEMO-LOT-001', productId: 'p4', location: 'Demo North Store', physical: 20, reserved: 4, unit: 'each' },
    { id: 'lot-2', reference: 'DEMO-LOT-002', productId: 'p5', location: 'Demo South Store', physical: 12, reserved: 2, unit: 'each' },
    { id: 'lot-3', reference: 'DEMO-LOT-003', productId: 'p4', location: 'Demo South Store', physical: 8, reserved: 0, unit: 'each' },
  ],
  receipts: [
    { id: 'receipt-1', receivedDate: '2026-01-12', receivedBy: 'Demo Receiver A', quantity: 4, location: 'Demo North Store', specifications: 'Illustrative device delivery' },
    { id: 'receipt-2', receivedDate: '2026-02-03', receivedBy: 'Demo Receiver B', quantity: 8, location: 'Demo South Store', specifications: 'Illustrative accessory delivery' },
  ],
}

/** Local-only provider. Never falls back from a failed production request. */
export const mockAssetProvider: AssetPreviewProvider = {
  mode: 'fictional-mock',
  load: async () => data,
}
