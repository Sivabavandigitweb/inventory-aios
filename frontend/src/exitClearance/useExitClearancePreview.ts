import { useEffect, useState } from 'react'
import { mockAssetProvider } from '../assets/mockAssetProvider'
import type { AssetPreviewProvider } from '../assets/types'
import { mockEmployeeProvider } from '../employees/mockEmployeeProvider'
import type { EmployeeDirectoryProvider } from '../employees/types'
import { mockWorkflowProvider } from '../workflows/mockWorkflowProvider'
import type { WorkflowPreviewProvider } from '../workflows/types'
import { validateWorkflowBundle, type WorkflowBundle } from '../workflows/useWorkflowPreview'
import { mockExitClearanceProvider } from './mockExitClearanceProvider'
import type { ExitClearancePreviewData, ExitClearancePreviewProvider } from './types'
import { validateExitClearancePreview } from './validation'
export type ExitClearanceProviders = { assetProvider?: AssetPreviewProvider; employeeProvider?: EmployeeDirectoryProvider; workflowProvider?: WorkflowPreviewProvider; clearanceProvider?: ExitClearancePreviewProvider }
type Loaded = WorkflowBundle & { clearance: ExitClearancePreviewData }
export function useExitClearancePreview({ assetProvider = mockAssetProvider, employeeProvider = mockEmployeeProvider, workflowProvider = mockWorkflowProvider, clearanceProvider = mockExitClearanceProvider }: ExitClearanceProviders) {
  const [data, setData] = useState<Loaded | null>(null); const [loading, setLoading] = useState(true); const [error, setError] = useState(false); const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    let current = true
    Promise.all([assetProvider.load(), employeeProvider.listEmployees({ offset: 0, limit: 1000 }), workflowProvider.load(), clearanceProvider.load()]).then(([assets, page, workflow, clearance]) => {
      if (!current) return
      if (page.total !== page.items.length) throw new Error('Incomplete employee preview')
      const bundle = { assets, employees: page.items, workflow }; validateWorkflowBundle(bundle); validateExitClearancePreview(bundle, clearance)
      setData({ ...bundle, clearance }); setError(false); setLoading(false)
    }).catch(() => { if (current) { setData(null); setError(true); setLoading(false) } })
    return () => { current = false }
  }, [assetProvider, employeeProvider, workflowProvider, clearanceProvider, attempt])
  return { data, loading, error, retry: () => { setLoading(true); setAttempt((value) => value + 1) } }
}
