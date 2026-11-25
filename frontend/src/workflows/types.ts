/** Fictional allocation/return preview contracts; no backend workflow schema exists. */
export type AllocationPreview = {
  reference: string
  employeeId: string
  assetId: string
  allocatedOn: string
  assignedBy: string
  conditionNote: string
}
export type ReturnPreview = {
  reference: string
  allocationReference: string
  returnedOn: string
  returnedBy: string
  verifiedBy: string
  conditionNote: string
  receivingLocation: string
  remarks: string
}
export type WorkflowPreviewData = { allocations: AllocationPreview[]; returns: ReturnPreview[] }
export type WorkflowPreviewProvider = { load(): Promise<WorkflowPreviewData> }
