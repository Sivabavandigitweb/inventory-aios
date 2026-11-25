import type { ApprovalNotificationPreviewData, ApprovalNotificationPreviewProvider } from './types'
const data: ApprovalNotificationPreviewData = {
  requests: [
    { reference: 'DEMO-APPROVAL-001', requestType: 'Asset registration', description: 'Illustrative registration review related to a receipt preview; no asset registration exists.', requestDate: '2026-04-02', receiptId: 'receipt-1' },
    { reference: 'DEMO-APPROVAL-002', requestType: 'Allocation', description: 'Illustrative request scenario for a fictional employee and available asset; no allocation is created.', requestDate: '2026-04-06', employeeId: '10000000-0000-4000-8000-000000000001', assetId: 'asset-6' },
    { reference: 'DEMO-APPROVAL-003', requestType: 'Return', description: 'Illustrative return review scenario for a currently allocated fictional asset.', requestDate: '2026-04-08', allocationReference: 'DEMO-ALLOC-001', assetId: 'asset-2', employeeId: '10000000-0000-4000-8000-000000000001' },
    { reference: 'DEMO-APPROVAL-004', requestType: 'Disposal', description: 'Illustrative disposal review scenario for a damaged fictional asset; no disposal is recorded.', requestDate: '2026-04-10', assetId: 'asset-11' },
  ],
  notifications: [
    { reference: 'DEMO-NOTICE-001', title: 'New receipt may need registration review', category: 'Pending asset registration', description: 'Illustrative reminder category from R-12; this receipt preview is not a live pending task.', receiptId: 'receipt-1' },
    { reference: 'DEMO-NOTICE-002', title: 'An allocated asset may be due for return', category: 'Assets pending return', description: 'Illustrative reminder category from R-12; no deadline or overdue status is assigned.', allocationReference: 'DEMO-ALLOC-001', assetId: 'asset-2' },
    { reference: 'DEMO-NOTICE-003', title: 'Warranty expiration reminder category', category: 'Warranty expiration', description: 'R-12 names this reminder. No warranty record, expiration date, or alert is present.' },
    { reference: 'DEMO-NOTICE-004', title: 'Approval review reminder category', category: 'Pending approvals', description: 'Illustrative category only; no approval request is actually pending.', approvalReference: 'DEMO-APPROVAL-001' },
    { reference: 'DEMO-NOTICE-005', title: 'Missing asset information reminder category', category: 'Missing asset information', description: 'R-12 names this reminder. No company record has been flagged as incomplete.' },
  ],
}
/** Local fixture only. It never sends a message or replaces a failed live provider. */
export const mockApprovalNotificationProvider: ApprovalNotificationPreviewProvider = { load: async () => data }
