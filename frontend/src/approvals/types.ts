/** Fictional approval/notification scenarios, not backend contracts or live events. */
export type ApprovalRequestType = 'Asset registration' | 'Allocation' | 'Return' | 'Disposal'
export type NotificationCategory = 'Pending asset registration' | 'Assets pending return' | 'Warranty expiration' | 'Pending approvals' | 'Missing asset information'
export type ApprovalPreviewRequest = { reference: string; requestType: ApprovalRequestType; description: string; requestDate: string; assetId?: string; employeeId?: string; allocationReference?: string; receiptId?: string }
export type NotificationPreview = { reference: string; title: string; category: NotificationCategory; description: string; assetId?: string; allocationReference?: string; receiptId?: string; approvalReference?: string }
export type ApprovalNotificationPreviewData = { requests: ApprovalPreviewRequest[]; notifications: NotificationPreview[] }
export type ApprovalNotificationPreviewProvider = { load(): Promise<ApprovalNotificationPreviewData> }
