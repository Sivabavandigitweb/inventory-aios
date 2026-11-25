/** Fictional repair preview only; not a backend contract or approved workflow state. */
export type RepairPreviewRecord = {
  reference: string
  assetId: string
  reportedIssue: string
  reportedDate: string
  reportedBy: string
  repairDate: string | null
  exampleGroup: 'Open example' | 'Historical example'
}
export type RepairPreviewData = { repairs: RepairPreviewRecord[] }
export type RepairPreviewProvider = { load(): Promise<RepairPreviewData> }
