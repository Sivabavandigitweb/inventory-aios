import { useEffect, useState } from 'react'
import { mockAssetProvider } from '../assets/mockAssetProvider'
import type { AssetPreviewData, AssetPreviewProvider, PreviewAsset, PreviewProduct } from '../assets/types'
import { mockEmployeeProvider } from '../employees/mockEmployeeProvider'
import type { Employee, EmployeeDirectoryProvider } from '../employees/types'
import { mockWorkflowProvider } from './mockWorkflowProvider'
import type { AllocationPreview, ReturnPreview, WorkflowPreviewData, WorkflowPreviewProvider } from './types'

export type WorkflowBundle = {
  assets: AssetPreviewData
  employees: Employee[]
  workflow: WorkflowPreviewData
}
export type WorkflowProviders = {
  assetProvider?: AssetPreviewProvider
  employeeProvider?: EmployeeDirectoryProvider
  workflowProvider?: WorkflowPreviewProvider
}
export function employeeFor(bundle: WorkflowBundle, id: string) {
  return bundle.employees.find((employee) => employee.id === id)
}
export function assetFor(bundle: WorkflowBundle, id: string): PreviewAsset | undefined {
  return bundle.assets.assets.find((asset) => asset.id === id)
}
export function productFor(bundle: WorkflowBundle, assetId: string): PreviewProduct | undefined {
  const asset = assetFor(bundle, assetId)
  return bundle.assets.products.find((product) => product.id === asset?.productId)
}
export function returnFor(bundle: WorkflowBundle, allocationReference: string): ReturnPreview | undefined {
  return bundle.workflow.returns.find((item) => item.allocationReference === allocationReference)
}
export function allocationFor(bundle: WorkflowBundle, reference: string): AllocationPreview | undefined {
  return bundle.workflow.allocations.find((item) => item.reference === reference)
}
export function employeeName(employee: Employee | undefined): string {
  return employee ? employee.first_name + ' ' + employee.last_name : 'Unknown preview employee'
}

/** Reject inconsistent fictional links rather than displaying misleading custody. */
export function validateWorkflowBundle(bundle: WorkflowBundle): void {
  const { allocations, returns } = bundle.workflow
  const allocationRefs = new Set<string>()
  const returnRefs = new Set<string>()
  const returnedAllocations = new Set<string>()
  for (const allocation of allocations) {
    if (allocationRefs.has(allocation.reference) || !employeeFor(bundle, allocation.employeeId) || !assetFor(bundle, allocation.assetId)) {
      throw new Error('Invalid fictional workflow references')
    }
    allocationRefs.add(allocation.reference)
  }
  for (const item of returns) {
    const allocation = allocationFor(bundle, item.allocationReference)
    if (returnRefs.has(item.reference) || returnedAllocations.has(item.allocationReference)
      || !allocation || item.returnedOn < allocation.allocatedOn) {
      throw new Error('Invalid fictional workflow references')
    }
    returnRefs.add(item.reference)
    returnedAllocations.add(item.allocationReference)
  }
  const byAsset = new Map<string, AllocationPreview[]>()
  for (const allocation of allocations) {
    const group = byAsset.get(allocation.assetId) ?? []
    group.push(allocation)
    byAsset.set(allocation.assetId, group)
  }
  for (const [assetId, group] of byAsset) {
    const ordered = group.sort((a, b) => a.allocatedOn.localeCompare(b.allocatedOn))
    const current = ordered.filter((allocation) => !returnedAllocations.has(allocation.reference))
    if (current.length > 1 || (current.length === 1 && assetFor(bundle, assetId)?.status !== 'Allocated')) {
      throw new Error('Conflicting fictional custody')
    }
    for (let index = 0; index < ordered.length - 1; index += 1) {
      const priorReturn = returnFor(bundle, ordered[index].reference)
      if (!priorReturn || priorReturn.returnedOn >= ordered[index + 1].allocatedOn) {
        throw new Error('Conflicting fictional custody')
      }
    }
  }
}

export function useWorkflowPreview({
  assetProvider = mockAssetProvider,
  employeeProvider = mockEmployeeProvider,
  workflowProvider = mockWorkflowProvider,
}: WorkflowProviders) {
  const [data, setData] = useState<WorkflowBundle | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    let current = true
    Promise.all([
      assetProvider.load(),
      employeeProvider.listEmployees({ offset: 0, limit: 1000 }),
      workflowProvider.load(),
    ]).then(([assets, employeePage, workflow]) => {
      if (!current) return
      if (employeePage.total !== employeePage.items.length) throw new Error('Incomplete fictional employee preview')
      const next = { assets, employees: employeePage.items, workflow }
      validateWorkflowBundle(next)
      setData(next)
      setError(false)
      setLoading(false)
    }).catch(() => {
      if (!current) return
      setData(null)
      setError(true)
      setLoading(false)
    })
    return () => { current = false }
  }, [assetProvider, employeeProvider, workflowProvider, retry])
  return { data, loading, error, retry: () => { setLoading(true); setRetry((value) => value + 1) } }
}
