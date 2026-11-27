import type { EmployeeDirectoryProvider, EmployeeFilters, EmployeePageResult, EmployeeSummary } from './types'

const base = '/api/v1/employees'

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { credentials: 'same-origin', headers: { Accept: 'application/json' } })
  if (!response.ok) throw new Error('Employee service is unavailable.')
  return response.json() as Promise<T>
}

/** Real API provider for the authenticated workspace; never substitutes preview data. */
export const apiEmployeeProvider: EmployeeDirectoryProvider = {
  mode: 'authenticated-api',
  departments: [],
  teams: [],
  designations: [],
  statuses: [{ value: 'active', label: 'Active' }, { value: 'inactive', label: 'Inactive' }],
  listEmployees(filters: EmployeeFilters): Promise<EmployeePageResult> {
    const query = new URLSearchParams()
    for (const [key, value] of Object.entries(filters)) if (value !== undefined) query.set(key, String(value))
    return getJson(`${base}?${query.toString()}`)
  },
  getSummary(): Promise<EmployeeSummary> {
    return getJson(`${base}/summary`)
  },
}
