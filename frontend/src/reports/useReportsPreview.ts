import { useEffect, useState } from 'react'
import { mockAssetProvider } from '../assets/mockAssetProvider'
import type { AssetPreviewProvider } from '../assets/types'
import { mockEmployeeProvider } from '../employees/mockEmployeeProvider'
import type { EmployeeDirectoryProvider } from '../employees/types'
import { mockWorkflowProvider } from '../workflows/mockWorkflowProvider'
import type { WorkflowPreviewProvider } from '../workflows/types'
import { validateWorkflowBundle, type WorkflowBundle } from '../workflows/useWorkflowPreview'
import { mockRepairProvider } from '../repairs/mockRepairProvider'
import type { RepairPreviewProvider } from '../repairs/types'
import { mockExitClearanceProvider } from '../exitClearance/mockExitClearanceProvider'
import type { ExitClearancePreviewProvider } from '../exitClearance/types'
import { validateExitClearancePreview } from '../exitClearance/validation'
import { mockApprovalNotificationProvider } from '../approvals/mockApprovalNotificationProvider'
import type { ApprovalNotificationPreviewProvider } from '../approvals/types'
import { validateApprovalPreview } from '../approvals/validation'
import type { ReportData } from './selectors'

export type ReportsProviders = { assetProvider?: AssetPreviewProvider; employeeProvider?: EmployeeDirectoryProvider; workflowProvider?: WorkflowPreviewProvider; repairProvider?: RepairPreviewProvider; clearanceProvider?: ExitClearancePreviewProvider; approvalProvider?: ApprovalNotificationPreviewProvider }
export function useReportsPreview({ assetProvider = mockAssetProvider, employeeProvider = mockEmployeeProvider, workflowProvider = mockWorkflowProvider, repairProvider = mockRepairProvider, clearanceProvider = mockExitClearanceProvider, approvalProvider = mockApprovalNotificationProvider }: ReportsProviders) {
  const [data, setData] = useState<ReportData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    let active = true
    Promise.all([assetProvider.load(), employeeProvider.listEmployees({ offset: 0, limit: 1000 }), workflowProvider.load(), repairProvider.load(), clearanceProvider.load(), approvalProvider.load()]).then(([assets, page, workflows, repairs, clearances, approvals]) => {
      if (!active) return
      if (page.total !== page.items.length) throw new Error('Incomplete preview directory')
      const bundle: WorkflowBundle = { assets, employees: page.items, workflow: workflows }
      validateWorkflowBundle(bundle)
      validateExitClearancePreview(bundle, clearances)
      validateApprovalPreview(bundle, approvals)
      if (repairs.repairs.some((repair) => !assets.assets.some((asset) => asset.id === repair.assetId))) throw new Error('Invalid repair preview reference')
      setData({ assets, employees: page.items, workflows, repairs, clearances, approvals, departments: employeeProvider.departments })
      setError(false)
      setLoading(false)
    }).catch(() => {
      if (active) { setData(null); setError(true); setLoading(false) }
    })
    return () => { active = false }
  }, [assetProvider, employeeProvider, workflowProvider, repairProvider, clearanceProvider, approvalProvider, attempt])
  return { data, loading, error, retry: () => { setLoading(true); setAttempt((value) => value + 1) } }
}
