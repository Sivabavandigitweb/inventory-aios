import type { RepairPreviewData, RepairPreviewProvider } from './types'
const data: RepairPreviewData = { repairs: [
  { reference: 'DEMO-REPAIR-001', assetId: 'asset-4', reportedIssue: 'Illustrative intermittent display issue', reportedDate: '2026-04-02', reportedBy: 'Demo Officer', repairDate: null, exampleGroup: 'Open example' },
  { reference: 'DEMO-REPAIR-002', assetId: 'asset-9', reportedIssue: 'Illustrative chair adjustment issue', reportedDate: '2026-04-08', reportedBy: 'Demo Officer', repairDate: null, exampleGroup: 'Open example' },
  { reference: 'DEMO-REPAIR-003', assetId: 'asset-1', reportedIssue: 'Illustrative keyboard connection issue', reportedDate: '2025-03-10', reportedBy: 'Demo Officer', repairDate: '2025-03-13', exampleGroup: 'Historical example' },
  { reference: 'DEMO-REPAIR-004', assetId: 'asset-6', reportedIssue: 'Illustrative display connection issue', reportedDate: '2025-03-05', reportedBy: 'Demo Officer', repairDate: '2025-03-08', exampleGroup: 'Historical example' },
  { reference: 'DEMO-REPAIR-005', assetId: 'asset-8', reportedIssue: 'Illustrative power issue', reportedDate: '2025-05-10', reportedBy: 'Demo Officer', repairDate: '2025-05-15', exampleGroup: 'Historical example' },
  { reference: 'DEMO-REPAIR-006', assetId: 'asset-12', reportedIssue: 'Illustrative connection issue', reportedDate: '2025-08-04', reportedBy: 'Demo Officer', repairDate: '2025-08-08', exampleGroup: 'Historical example' },
] }
/** Local-only fictional fixture. Provider failures are surfaced, never replaced with these rows. */
export const mockRepairProvider: RepairPreviewProvider = { load: async () => data }
