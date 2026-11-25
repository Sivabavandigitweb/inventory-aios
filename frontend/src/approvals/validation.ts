import type { WorkflowBundle } from '../workflows/useWorkflowPreview'
import type { ApprovalNotificationPreviewData } from './types'
export function validateApprovalPreview(bundle: WorkflowBundle, data: ApprovalNotificationPreviewData): void {
  const requestRefs = new Set<string>()
  const notificationRefs = new Set<string>()
  for (const request of data.requests) {
    if (requestRefs.has(request.reference)) throw new Error('Duplicate fictional approval reference')
    if (request.assetId && !bundle.assets.assets.some((asset) => asset.id === request.assetId)) throw new Error('Invalid fictional approval asset reference')
    if (request.employeeId && !bundle.employees.some((employee) => employee.id === request.employeeId)) throw new Error('Invalid fictional approval employee reference')
    if (request.receiptId && !bundle.assets.receipts.some((receipt) => receipt.id === request.receiptId)) throw new Error('Invalid fictional approval receipt reference')
    if (request.allocationReference) {
      const allocation = bundle.workflow.allocations.find((item) => item.reference === request.allocationReference)
      if (!allocation || (request.assetId && allocation.assetId !== request.assetId) || (request.employeeId && allocation.employeeId !== request.employeeId)) throw new Error('Invalid fictional approval allocation reference')
    }
    requestRefs.add(request.reference)
  }
  for (const item of data.notifications) {
    if (notificationRefs.has(item.reference) || (item.assetId && !bundle.assets.assets.some((asset) => asset.id === item.assetId))
      || (item.receiptId && !bundle.assets.receipts.some((receipt) => receipt.id === item.receiptId))
      || (item.approvalReference && !requestRefs.has(item.approvalReference))) throw new Error('Invalid fictional notification reference')
    if (item.allocationReference) {
      const allocation = bundle.workflow.allocations.find((entry) => entry.reference === item.allocationReference)
      if (!allocation || (item.assetId && allocation.assetId !== item.assetId)) throw new Error('Invalid fictional notification allocation reference')
    }
    notificationRefs.add(item.reference)
  }
}
