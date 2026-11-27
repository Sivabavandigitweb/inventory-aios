export type CategoryOption = { id: string; code: string; name: string; tracking_mode: 'individual' | 'quantity' }
export type LocationOption = { id: string; code: string; name: string }
export type ProductOption = { id: string; category_id: string; name: string; active: boolean }
export type RegistrationCandidate = {
  id: string
  receipt_id: string
  product_id: string
  product_name: string
  location_name: string
  tracking_mode: 'individual' | 'quantity'
  quantity: string
  unit: string
  remaining_quantity: string
}
export type RegistrationApproval = {
  id: string
  entity_type: string
  entity_id: string
  required_capability: string
  requested_by_id: string
  created_at: string
}
export type RegistrationFinalization = {
  request_id: string
  tracking_mode: 'individual' | 'quantity'
  product_name: string
  quantity: string
  unit: string
}
export type WriteResult = { id: string; status: string; replayed: boolean }

export interface InventoryWriteProvider {
  loadCategories(): Promise<CategoryOption[]>
  loadLocations(): Promise<LocationOption[]>
  loadProducts(): Promise<ProductOption[]>
  loadCandidates(mode: 'individual' | 'quantity'): Promise<RegistrationCandidate[]>
  loadApprovals(): Promise<RegistrationApproval[]>
  loadFinalizations(): Promise<RegistrationFinalization[]>
  createProduct(input: { category_id: string; name: string; sku?: string; brand?: string; model?: string }, csrfToken: string): Promise<WriteResult>
  createReceipt(input: { received_at: string; location_id: string; lines: Array<{ product_id: string; quantity: string; unit: string; tracking_mode: 'individual' | 'quantity' }> }, csrfToken: string): Promise<WriteResult>
  submitAssetRegistration(input: { receipt_line_id: string; asset_number?: string; serial_number?: string }, csrfToken: string): Promise<WriteResult>
  submitQuantityRegistration(input: { receipt_line_id: string; quantity: string; unit: string }, csrfToken: string): Promise<WriteResult>
  decideApproval(id: string, decision: 'approved' | 'rejected', csrfToken: string): Promise<void>
  finalizeRegistration(requestId: string, mode: 'individual' | 'quantity', csrfToken: string): Promise<WriteResult>
}

async function read<T>(path: string): Promise<T> {
  const response = await fetch(`/api/v1/inventory/${path}`, {
    credentials: 'same-origin', cache: 'no-store', headers: { Accept: 'application/json' },
  })
  if (!response.ok) throw new Error('Inventory service is unavailable.')
  return response.json() as Promise<T>
}

async function write<T>(path: string, body: unknown, csrfToken: string): Promise<T> {
  if (!csrfToken) throw new Error('A verified session is required.')
  const response = await fetch(`/api/v1/inventory/${path}`, {
    method: 'POST', credentials: 'same-origin', cache: 'no-store',
    headers: {
      Accept: 'application/json', 'Content-Type': 'application/json',
      'X-CSRF-Token': csrfToken, 'Idempotency-Key': crypto.randomUUID(),
    },
    body: JSON.stringify(body),
  })
  if (!response.ok) throw new Error('The inventory operation could not be confirmed.')
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

/** Same-origin, cookie-authenticated API adapter. It never substitutes preview data. */
export const apiInventoryWriteProvider: InventoryWriteProvider = {
  loadCategories: () => read('categories'),
  loadLocations: () => read('locations'),
  loadProducts: async () => (await read<{ items: ProductOption[] }>('products?limit=100&offset=0')).items,
  loadCandidates: (mode) => read(`registration-candidates?tracking_mode=${mode}`),
  loadApprovals: () => read('registration-approvals'),
  loadFinalizations: () => read('registration-finalizations'),
  createProduct: (input, csrf) => write('products', input, csrf),
  createReceipt: (input, csrf) => write('receipts', input, csrf),
  submitAssetRegistration: (input, csrf) => write(`receipt-lines/${input.receipt_line_id}/asset-registration`, input, csrf),
  submitQuantityRegistration: (input, csrf) => write(`receipt-lines/${input.receipt_line_id}/quantity-registration`, input, csrf),
  decideApproval: async (id, decision, csrf) => { await write(`registration-approvals/${id}/decision`, { decision }, csrf) },
  finalizeRegistration: (id, mode, csrf) => write(`${mode === 'individual' ? 'asset' : 'quantity'}-registration-requests/${id}/finalize`, {}, csrf),
}
