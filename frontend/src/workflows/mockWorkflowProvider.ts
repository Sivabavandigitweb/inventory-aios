import type { AllocationPreview, ReturnPreview, WorkflowPreviewData, WorkflowPreviewProvider } from './types'

const allocations: AllocationPreview[] = [
  { reference: 'DEMO-ALLOC-001', employeeId: '10000000-0000-4000-8000-000000000001', assetId: 'asset-2', allocatedOn: '2026-03-01', assignedBy: 'Demo Officer', conditionNote: 'Illustrative observation' },
  { reference: 'DEMO-ALLOC-002', employeeId: '10000000-0000-4000-8000-000000000003', assetId: 'asset-7', allocatedOn: '2026-03-10', assignedBy: 'Demo Officer', conditionNote: 'Illustrative observation' },
  { reference: 'DEMO-ALLOC-003', employeeId: '10000000-0000-4000-8000-000000000002', assetId: 'asset-1', allocatedOn: '2025-01-12', assignedBy: 'Demo Officer', conditionNote: 'Illustrative observation' },
  { reference: 'DEMO-ALLOC-004', employeeId: '10000000-0000-4000-8000-000000000004', assetId: 'asset-6', allocatedOn: '2025-02-02', assignedBy: 'Demo Officer', conditionNote: 'Illustrative observation' },
  { reference: 'DEMO-ALLOC-005', employeeId: '10000000-0000-4000-8000-000000000005', assetId: 'asset-8', allocatedOn: '2025-04-06', assignedBy: 'Demo Officer', conditionNote: 'Illustrative observation' },
  { reference: 'DEMO-ALLOC-006', employeeId: '10000000-0000-4000-8000-000000000006', assetId: 'asset-10', allocatedOn: '2025-06-12', assignedBy: 'Demo Officer', conditionNote: 'Illustrative observation' },
  { reference: 'DEMO-ALLOC-007', employeeId: '10000000-0000-4000-8000-000000000007', assetId: 'asset-12', allocatedOn: '2025-07-01', assignedBy: 'Demo Officer', conditionNote: 'Illustrative observation' },
  { reference: 'DEMO-ALLOC-008', employeeId: '10000000-0000-4000-8000-000000000008', assetId: 'asset-1', allocatedOn: '2025-09-02', assignedBy: 'Demo Officer', conditionNote: 'Illustrative observation' },
]
const returns: ReturnPreview[] = [
  { reference: 'DEMO-RETURN-001', allocationReference: 'DEMO-ALLOC-003', returnedOn: '2025-02-15', returnedBy: 'Demo Returner', verifiedBy: 'Demo Verifier', conditionNote: 'Illustrative inspection', receivingLocation: 'Demo North Store', remarks: 'Fictional example' },
  { reference: 'DEMO-RETURN-002', allocationReference: 'DEMO-ALLOC-004', returnedOn: '2025-03-01', returnedBy: 'Demo Returner', verifiedBy: 'Demo Verifier', conditionNote: 'Illustrative inspection', receivingLocation: 'Demo South Store', remarks: 'Fictional example' },
  { reference: 'DEMO-RETURN-003', allocationReference: 'DEMO-ALLOC-005', returnedOn: '2025-05-09', returnedBy: 'Demo Returner', verifiedBy: 'Demo Verifier', conditionNote: 'Illustrative inspection', receivingLocation: 'Demo South Store', remarks: 'Fictional example' },
  { reference: 'DEMO-RETURN-004', allocationReference: 'DEMO-ALLOC-006', returnedOn: '2025-06-30', returnedBy: 'Demo Returner', verifiedBy: 'Demo Verifier', conditionNote: 'Illustrative inspection', receivingLocation: 'Demo South Store', remarks: 'Fictional example' },
  { reference: 'DEMO-RETURN-005', allocationReference: 'DEMO-ALLOC-007', returnedOn: '2025-08-03', returnedBy: 'Demo Returner', verifiedBy: 'Demo Verifier', conditionNote: 'Illustrative inspection', receivingLocation: 'Demo South Store', remarks: 'Fictional example' },
  { reference: 'DEMO-RETURN-006', allocationReference: 'DEMO-ALLOC-008', returnedOn: '2025-10-04', returnedBy: 'Demo Returner', verifiedBy: 'Demo Verifier', conditionNote: 'Illustrative inspection', receivingLocation: 'Demo North Store', remarks: 'Fictional example' },
]
const data: WorkflowPreviewData = { allocations, returns }

/** Partial fictional examples only. No operational or complete-history claims. */
export const mockWorkflowProvider: WorkflowPreviewProvider = { load: async () => data }
