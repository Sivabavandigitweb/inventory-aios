import type { WorkflowBundle } from '../workflows/useWorkflowPreview'
import type { ExitClearancePreviewCase } from './types'
export function clearanceCaseSummary(bundle: WorkflowBundle, item: ExitClearancePreviewCase) {
  const allocations = bundle.workflow.allocations.filter((allocation) => allocation.employeeId === item.employeeId).map((allocation) => {
    const returned = bundle.workflow.returns.find((entry) => entry.allocationReference === allocation.reference)
    return { allocation, returned, asset: bundle.assets.assets.find((asset) => asset.id === allocation.assetId), outstanding: !returned }
  })
  return { allocations, outstanding: allocations.filter((item) => item.outstanding), returns: allocations.filter((item) => item.returned).map((item) => item.returned!) }
}
