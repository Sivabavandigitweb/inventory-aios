export type EmployeeOption = { id: string; employee_number: string; first_name: string; last_name: string; status: string }
export type AssetOption = { id: string; asset_number: string | null; product_name: string; lifecycle_status: string }
export type BalanceOption = { product_id: string; product_name: string; location_id: string; location_name: string; unit: string; on_hand: string; reserved: string; quarantined: string; available: string }
export type AllocationRow = { id: string; employee_id: string; status: string; line_id: string; tracked_asset_id: string | null; product_id: string | null; location_id: string | null; unit: string | null; quantity: string; returned_quantity: string; line_status: string; created_at: string }
export type ReturnRow = { id: string; allocation_line_id: string; quantity: string; condition: string; status: string; recorded_by_id: string; created_at: string }
export type TransactionApi = {
  employees(): Promise<EmployeeOption[]>
  assets(): Promise<AssetOption[]>
  balances(): Promise<BalanceOption[]>
  allocations(): Promise<AllocationRow[]>
  returns(): Promise<ReturnRow[]>
  createAllocation(input: Record<string, string>, csrf: string): Promise<void>
  issueAllocation(id: string, csrf: string): Promise<void>
  decideAllocation(id: string, decision: 'approved' | 'rejected', csrf: string): Promise<void>
  createReturn(input: { allocation_line_id: string; quantity: string; condition: string }, csrf: string): Promise<void>
  decideReturn(id: string, decision: 'approved' | 'rejected', csrf: string): Promise<void>
}

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`/api/v1/${path}`, { credentials: 'same-origin', cache: 'no-store', headers: { Accept: 'application/json' } })
  if (!response.ok) throw new Error('The inventory service is unavailable.')
  return response.json() as Promise<T>
}
async function post(path: string, body: unknown, csrf: string): Promise<void> {
  if (!csrf) throw new Error('A verified session is required.')
  const response = await fetch(`/api/v1/inventory/${path}`, {
    method: 'POST', credentials: 'same-origin', cache: 'no-store',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json', 'X-CSRF-Token': csrf, 'Idempotency-Key': crypto.randomUUID() },
    body: JSON.stringify(body),
  })
  if (!response.ok) throw new Error('The inventory operation could not be confirmed.')
}

export const apiTransactionProvider: TransactionApi = {
  employees: async () => (await get<{ items: EmployeeOption[] }>('employees?status=active&limit=100&offset=0')).items,
  assets: async () => (await get<{ items: AssetOption[] }>('inventory/assets?lifecycle_status=available&limit=100&offset=0')).items,
  balances: () => get('inventory/quantity-balances'),
  allocations: () => get('inventory/allocations'),
  returns: () => get('inventory/returns'),
  createAllocation: (input, csrf) => post('allocations', input, csrf),
  issueAllocation: (id, csrf) => post(`allocations/${id}/issue`, {}, csrf),
  decideAllocation: (id, decision, csrf) => post(`allocations/${id}/decision`, { decision }, csrf),
  createReturn: (input, csrf) => post('returns', input, csrf),
  decideReturn: (id, decision, csrf) => post(`returns/${id}/decision`, { decision }, csrf),
}
