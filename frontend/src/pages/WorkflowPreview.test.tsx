import { describe, expect, it } from 'vitest'
import { mockAssetProvider } from '../assets/mockAssetProvider'
import { mockEmployeeProvider } from '../employees/mockEmployeeProvider'
import { mockWorkflowProvider } from '../workflows/mockWorkflowProvider'
import { validateWorkflowBundle } from '../workflows/useWorkflowPreview'

describe('fictional workflow references', () => {
  it('links allocations and returns to shared-provider records without conflicting custody', async () => {
    const assets = await mockAssetProvider.load()
    const employees = (await mockEmployeeProvider.listEmployees({ offset: 0, limit: 1000 })).items
    const workflow = await mockWorkflowProvider.load()
    const bundle = { assets, employees, workflow }
    expect(() => validateWorkflowBundle(bundle)).not.toThrow()
    expect(workflow.allocations).toHaveLength(8)
    expect(workflow.returns).toHaveLength(6)
    for (const allocation of workflow.allocations) {
      expect(employees.some((item) => item.id === allocation.employeeId)).toBe(true)
      expect(assets.assets.some((item) => item.id === allocation.assetId)).toBe(true)
    }
    for (const item of workflow.returns) {
      expect(workflow.allocations.some((allocation) => allocation.reference === item.allocationReference)).toBe(true)
    }
    const current = workflow.allocations.filter((item) => !workflow.returns.some((returned) => returned.allocationReference === item.reference))
    expect(current.map((item) => item.assetId)).toEqual(['asset-2', 'asset-7'])
    expect(new Set(current.map((item) => item.assetId)).size).toBe(current.length)
  })

  it('rejects missing references and overlapping fictional custody', async () => {
    const assets = await mockAssetProvider.load()
    const employees = (await mockEmployeeProvider.listEmployees({ offset: 0, limit: 1000 })).items
    const workflow = await mockWorkflowProvider.load()
    const first = workflow.allocations[0]
    expect(() => validateWorkflowBundle({ assets, employees, workflow: {
      ...workflow, allocations: [{ ...first, employeeId: 'missing' }, ...workflow.allocations.slice(1)],
    } })).toThrow('Invalid fictional workflow references')
    expect(() => validateWorkflowBundle({ assets, employees, workflow: {
      ...workflow, allocations: [...workflow.allocations, { ...first, reference: 'DEMO-DUPLICATE' }],
    } })).toThrow('Conflicting fictional custody')
  })
})