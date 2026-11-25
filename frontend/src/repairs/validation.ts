import { assetFor, type WorkflowBundle } from '../workflows/useWorkflowPreview'
import type { RepairPreviewData } from './types'

export function validateRepairPreview(bundle: WorkflowBundle, data: RepairPreviewData): void {
  const references = new Set<string>()
  const openAssets = new Set<string>()
  const currentAllocations = new Set(bundle.workflow.allocations
    .filter((allocation) => !bundle.workflow.returns.some((item) => item.allocationReference === allocation.reference))
    .map((allocation) => allocation.assetId))
  for (const repair of data.repairs) {
    const asset = assetFor(bundle, repair.assetId)
    if (!asset || references.has(repair.reference) || repair.reportedDate.length !== 10
      || (repair.exampleGroup === 'Open example' && (repair.repairDate !== null || !['Repair', 'Damaged'].includes(asset.status)
        || currentAllocations.has(repair.assetId) || openAssets.has(repair.assetId)))) {
      throw new Error('Invalid fictional repair references or custody')
    }
    references.add(repair.reference)
    if (repair.exampleGroup === 'Open example') openAssets.add(repair.assetId)
  }
}
