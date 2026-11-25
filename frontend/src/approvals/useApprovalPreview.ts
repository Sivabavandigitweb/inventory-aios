import { useEffect, useState } from 'react'
import { mockAssetProvider } from '../assets/mockAssetProvider'
import type { AssetPreviewProvider } from '../assets/types'
import { mockEmployeeProvider } from '../employees/mockEmployeeProvider'
import type { EmployeeDirectoryProvider } from '../employees/types'
import { mockWorkflowProvider } from '../workflows/mockWorkflowProvider'
import type { WorkflowPreviewProvider } from '../workflows/types'
import { validateWorkflowBundle, type WorkflowBundle } from '../workflows/useWorkflowPreview'
import { mockApprovalNotificationProvider } from './mockApprovalNotificationProvider'
import type { ApprovalNotificationPreviewData, ApprovalNotificationPreviewProvider } from './types'
import { validateApprovalPreview } from './validation'
export type ApprovalPreviewProviders = { assetProvider?: AssetPreviewProvider; employeeProvider?: EmployeeDirectoryProvider; workflowProvider?: WorkflowPreviewProvider; approvalProvider?: ApprovalNotificationPreviewProvider }
type Loaded = WorkflowBundle & { preview: ApprovalNotificationPreviewData }
export function useApprovalPreview({ assetProvider = mockAssetProvider, employeeProvider = mockEmployeeProvider, workflowProvider = mockWorkflowProvider, approvalProvider = mockApprovalNotificationProvider }: ApprovalPreviewProviders) {
  const [data, setData] = useState<Loaded | null>(null); const [loading, setLoading] = useState(true); const [error, setError] = useState(false); const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    let current = true
    Promise.all([assetProvider.load(), employeeProvider.listEmployees({ offset: 0, limit: 1000 }), workflowProvider.load(), approvalProvider.load()]).then(([assets, page, workflow, preview]) => {
      if (!current) return
      if (page.total !== page.items.length) throw new Error('Incomplete fictional employee preview')
      const bundle = { assets, employees: page.items, workflow }; validateWorkflowBundle(bundle); validateApprovalPreview(bundle, preview)
      setData({ ...bundle, preview }); setError(false); setLoading(false)
    }).catch(() => { if (current) { setData(null); setError(true); setLoading(false) } })
    return () => { current = false }
  }, [assetProvider, employeeProvider, workflowProvider, approvalProvider, attempt])
  return { data, loading, error, retry: () => { setLoading(true); setAttempt((value) => value + 1) } }
}
