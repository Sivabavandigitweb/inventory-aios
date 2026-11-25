import { describe, expect, it } from 'vitest'
import { mockEmployeeProvider } from './mockEmployeeProvider'

describe('fictional employee provider', () => {
  it('identifies mock mode and reports a consistent summary', async () => {
    expect(mockEmployeeProvider.mode).toBe('fictional-mock')
    expect(await mockEmployeeProvider.getSummary()).toEqual({
      total: 12,
      active: 9,
      inactive: 3,
      departments: 3,
    })
    expect(mockEmployeeProvider.statuses.map(({ value }) => value)).toEqual(['active', 'inactive'])
  })

  it('searches and paginates only fictional records', async () => {
    const page = await mockEmployeeProvider.listEmployees({ q: 'DEMO-003', limit: 5, offset: 0 })
    expect(page.total).toBe(1)
    expect(page.items.map(({ employee_number }) => employee_number)).toEqual(['DEMO-003'])

    const secondPage = await mockEmployeeProvider.listEmployees({ limit: 5, offset: 5 })
    expect(secondPage.items).toHaveLength(5)
    expect(secondPage.items.some(({ employee_number }) => employee_number === 'DEMO-001')).toBe(false)
  })
})