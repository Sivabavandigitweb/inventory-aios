import type { ExitClearancePreviewData, ExitClearancePreviewProvider } from './types'
const data: ExitClearancePreviewData = { cases: [
  { reference: 'DEMO-CLEARANCE-001', employeeId: '10000000-0000-4000-8000-000000000001' },
  { reference: 'DEMO-CLEARANCE-002', employeeId: '10000000-0000-4000-8000-000000000003' },
  { reference: 'DEMO-CLEARANCE-003', employeeId: '10000000-0000-4000-8000-000000000002' },
  { reference: 'DEMO-CLEARANCE-004', employeeId: '10000000-0000-4000-8000-000000000004' },
  { reference: 'DEMO-CLEARANCE-005', employeeId: '10000000-0000-4000-8000-000000000005' },
  { reference: 'DEMO-CLEARANCE-006', employeeId: '10000000-0000-4000-8000-000000000006' },
] }
/** Local-only partial sample; no employee status is used to create or complete a case. */
export const mockExitClearanceProvider: ExitClearancePreviewProvider = { load: async () => data }
