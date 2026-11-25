import type { WorkflowBundle } from '../workflows/useWorkflowPreview'
import type { ExitClearancePreviewData } from './types'
export function validateExitClearancePreview(bundle: WorkflowBundle, data: ExitClearancePreviewData): void {
  const seen = new Set<string>()
  for (const item of data.cases) {
    if (seen.has(item.reference) || !bundle.employees.some((employee) => employee.id === item.employeeId)) throw new Error('Invalid fictional clearance reference')
    seen.add(item.reference)
  }
}
