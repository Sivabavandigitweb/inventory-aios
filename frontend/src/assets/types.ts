/** Preview contracts only. These are not backend API response schemas. */
export type AssetStatus = 'Available' | 'Allocated' | 'Repair' | 'Damaged' | 'Disposed'

export type PreviewProduct = {
  id: string
  name: string
  category: string
  sku: string | null
  brand: string | null
  model: string | null
  specifications: string
  active: boolean
}
export type PreviewAsset = {
  id: string
  identifier: string
  productId: string
  location: string
  condition: string
  status: AssetStatus
}
export type PreviewLot = {
  id: string
  reference: string
  productId: string
  location: string
  physical: number
  reserved: number
  unit: string
}
export type PreviewReceipt = {
  id: string
  receivedDate: string
  receivedBy: string
  quantity: number | null
  location: string
  specifications: string
}
export type AssetPreviewData = {
  products: PreviewProduct[]
  assets: PreviewAsset[]
  lots: PreviewLot[]
  receipts: PreviewReceipt[]
}
export type AssetPreviewProvider = { mode?: 'fictional-mock' | 'authenticated-api'; load(): Promise<AssetPreviewData> }
