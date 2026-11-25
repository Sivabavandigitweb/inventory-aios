import { useEffect, useState } from 'react'
import { mockAssetProvider } from '../assets/mockAssetProvider'
import type { AssetPreviewProvider } from '../assets/types'
import { mockEmployeeProvider } from '../employees/mockEmployeeProvider'
import type { EmployeeDirectoryProvider } from '../employees/types'
import { mockWorkflowProvider } from '../workflows/mockWorkflowProvider'
import type { WorkflowPreviewProvider } from '../workflows/types'
import { validateWorkflowBundle } from '../workflows/useWorkflowPreview'
import { mockRepairProvider } from './mockRepairProvider'
import type { RepairPreviewData, RepairPreviewProvider } from './types'
import { validateRepairPreview } from './validation'
export type RepairPreviewProviders = { assetProvider?: AssetPreviewProvider; employeeProvider?: EmployeeDirectoryProvider; workflowProvider?: WorkflowPreviewProvider; repairProvider?: RepairPreviewProvider }
type Loaded = { assets: Awaited<ReturnType<AssetPreviewProvider['load']>>; employees: Awaited<ReturnType<EmployeeDirectoryProvider['listEmployees']>>['items']; workflow: Awaited<ReturnType<WorkflowPreviewProvider['load']>>; repairs: RepairPreviewData }
export function useRepairPreview({ assetProvider = mockAssetProvider, employeeProvider = mockEmployeeProvider, workflowProvider = mockWorkflowProvider, repairProvider = mockRepairProvider }: RepairPreviewProviders) {
  const [data, setData] = useState<Loaded | null>(null); const [loading, setLoading] = useState(true); const [error, setError] = useState(false); const [retryCount, setRetryCount] = useState(0)
  useEffect(() => {
    let current = true
    Promise.all([assetProvider.load(), employeeProvider.listEmployees({ offset: 0, limit: 1000 }), workflowProvider.load(), repairProvider.load()]).then(([assets, page, workflow, repairs]) => {
      if (!current) return
      if (page.total !== page.items.length) throw new Error('Incomplete fictional employee preview')
      const bundle = { assets, employees: page.items, workflow }; validateWorkflowBundle(bundle); validateRepairPreview(bundle, repairs)
      setData({ ...bundle, repairs }); setError(false); setLoading(false)
    }).catch(() => { if (current) { setData(null); setError(true); setLoading(false) } })
    return () => { current = false }
  }, [assetProvider, employeeProvider, workflowProvider, repairProvider, retryCount])
  return { data, loading, error, retry: () => { setLoading(true); setRetryCount((value) => value + 1) } }
}
