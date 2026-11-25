import type { AssetPreviewData } from '../assets/types'
import type { Employee } from '../employees/types'
import type { WorkflowBundle } from '../workflows/useWorkflowPreview'
import type { RepairPreviewData } from '../repairs/types'
import type { ExitClearancePreviewData } from '../exitClearance/types'
import type { ApprovalNotificationPreviewData } from '../approvals/types'

export type ReportKind = 'assets' | 'quantity' | 'employee' | 'department' | 'allocations' | 'returns' | 'repairs' | 'damaged' | 'exit' | 'approvals' | 'missing' | 'purchases' | 'audit'
export type ReportRow = {
  id: string
  reference: string
  subject: string
  details: string
  category: string
  location: string
  status: string
  employee: string
  department: string
  date: string
  href: string
}
export type ReportData = {
  assets: AssetPreviewData
  employees: Employee[]
  workflows: WorkflowBundle['workflow']
  repairs: RepairPreviewData
  clearances: ExitClearancePreviewData
  approvals: ApprovalNotificationPreviewData
  departments: readonly { id: string; name: string }[]
}
export type ReportDefinition = { id: ReportKind; label: string; requirement: string; available: boolean; reason?: string }
export const REPORTS: ReportDefinition[] = [
  { id: 'assets', label: 'Individual asset inventory', requirement: 'R-15 asset summary', available: true },
  { id: 'quantity', label: 'Quantity inventory and availability', requirement: 'Proposed preview', available: true },
  { id: 'employee', label: 'Employee-wise assets', requirement: 'R-15 employee-wise', available: true },
  { id: 'department', label: 'Department-wise assets', requirement: 'R-15 department-wise', available: true },
  { id: 'allocations', label: 'Allocation report', requirement: 'R-15 allocation', available: true },
  { id: 'returns', label: 'Return report', requirement: 'R-15 return', available: true },
  { id: 'repairs', label: 'Repair records', requirement: 'Proposed; R-09 workflow', available: true },
  { id: 'damaged', label: 'Damaged assets', requirement: 'R-15 damaged', available: true },
  { id: 'exit', label: 'Employee exit assets', requirement: 'R-15 employee exit asset', available: true },
  { id: 'approvals', label: 'Approval examples', requirement: 'Proposed; R-10 workflow', available: true },
  { id: 'missing', label: 'Missing asset information', requirement: 'Proposed; R-12 category', available: false, reason: 'No approved completeness rules or validated records are available. Missing fields cannot be inferred from this preview.' },
  { id: 'purchases', label: 'Purchase history', requirement: 'R-15 purchase history', available: false, reason: 'Purchase dates, supplier, cost, and currency are not present in the shared preview records.' },
  { id: 'audit', label: 'Audit trail', requirement: 'R-15 audit trail', available: false, reason: 'Authorized audit history is not connected. R-11 remains partially implemented.' },
]
const displayName = (employee: Employee) => employee.first_name + ' ' + employee.last_name
function departmentName(data: ReportData, employee: Employee) {
  return data.departments.find((item) => item.id === employee.department_id)?.name ?? 'Unknown department'
}
function employeeLabel(data: ReportData, id: string) {
  const person = data.employees.find((entry) => entry.id === id)
  return person ? displayName(person) + ' (' + person.employee_number + ')' : 'Unavailable'
}
function assetLabel(data: ReportData, assetId: string) {
  const asset = data.assets.assets.find((entry) => entry.id === assetId)
  const product = data.assets.products.find((entry) => entry.id === asset?.productId)
  return asset ? asset.identifier + ' - ' + (product?.name ?? 'Unmapped product') : 'Unknown asset'
}
export function buildReportRows(kind: ReportKind, data: ReportData): ReportRow[] {
  const products = new Map(data.assets.products.map((product) => [product.id, product]))
  if (kind === 'assets' || kind === 'damaged') return data.assets.assets.filter((asset) => kind !== 'damaged' || asset.status === 'Damaged').map((asset) => {
    const product = products.get(asset.productId)
    return { id: asset.id, reference: asset.identifier, subject: product?.name ?? 'Unmapped product', details: [product?.brand, product?.model, asset.condition].filter(Boolean).join(' - '), category: product?.category ?? 'Unmapped category', location: asset.location, status: asset.status, employee: '', department: '', date: '', href: '/assets?section=assets' }
  })
  if (kind === 'quantity') return data.assets.lots.map((lot) => {
    const product = products.get(lot.productId)
    return { id: lot.id, reference: lot.reference, subject: product?.name ?? 'Unmapped product', details: 'Physical ' + lot.physical + ' - Reserved ' + lot.reserved + ' - Available ' + (lot.physical - lot.reserved) + ' illustrative whole counts; unit unresolved', category: product?.category ?? 'Unmapped category', location: lot.location, status: 'Preview lot', employee: '', department: '', date: '', href: '/assets?section=quantity' }
  })
  if (kind === 'allocations' || kind === 'employee' || kind === 'department') {
    const allocations = data.workflows.allocations
    if (kind === 'allocations') return allocations.map((item) => {
      const person = data.employees.find((entry) => entry.id === item.employeeId)
      const asset = data.assets.assets.find((entry) => entry.id === item.assetId)
      return { id: item.reference, reference: item.reference, subject: assetLabel(data, item.assetId), details: 'Allocated ' + item.allocatedOn + ' - ' + item.conditionNote, category: '', location: asset?.location ?? '', status: 'Fictional allocation', employee: person ? displayName(person) + ' (' + person.employee_number + ')' : 'Unavailable', department: person ? departmentName(data, person) : '', date: item.allocatedOn, href: '/allocations' }
    })
    const groups = new Map<string, { count: number; labels: string[] }>()
    if (kind === 'employee') for (const person of data.employees) groups.set(displayName(person) + ' (' + person.employee_number + ')', { count: 0, labels: [] })
    if (kind === 'department') for (const person of data.employees) { const name = departmentName(data, person); if (!groups.has(name)) groups.set(name, { count: 0, labels: [] }) }
    for (const item of allocations) {
      const person = data.employees.find((entry) => entry.id === item.employeeId)
      const key = kind === 'employee' ? (person ? displayName(person) + ' (' + person.employee_number + ')' : 'Unknown employee') : (person ? departmentName(data, person) : 'Unknown department')
      const group = groups.get(key) ?? { count: 0, labels: [] }
      group.count += 1; group.labels.push(assetLabel(data, item.assetId)); groups.set(key, group)
    }
    return [...groups].map(([name, group]) => ({ id: name, reference: name, subject: name, details: group.count + ' fictional allocation records; ' + group.labels.join(', '), category: '', location: '', status: 'Preview summary', employee: kind === 'employee' ? name : '', department: kind === 'department' ? name : '', date: '', href: kind === 'employee' ? '/employees' : '/employees' }))
  }
  if (kind === 'repairs') return data.repairs.repairs.map((item) => {
    const asset = data.assets.assets.find((entry) => entry.id === item.assetId)
    const product = data.assets.products.find((entry) => entry.id === asset?.productId)
    return { id: item.reference, reference: item.reference, subject: asset?.identifier + ' - ' + (product?.name ?? 'Unknown product'), details: item.reportedIssue, category: product?.category ?? '', location: asset?.location ?? '', status: item.exampleGroup, employee: '', department: '', date: item.reportedDate, href: '/repairs' }
  })
  if (kind === 'returns') return data.workflows.returns.map((item) => {
    const allocation = data.workflows.allocations.find((entry) => entry.reference === item.allocationReference)
    const person = allocation && data.employees.find((entry) => entry.id === allocation.employeeId)
    return { id: item.reference, reference: item.reference, subject: allocation ? assetLabel(data, allocation.assetId) : 'Unavailable', details: 'Return example; verification semantics are not established', category: '', location: item.receivingLocation, status: 'Fictional return', employee: person ? displayName(person) + ' (' + person.employee_number + ')' : '', department: person ? departmentName(data, person) : '', date: item.returnedOn, href: '/returns' }
  })
  if (kind === 'exit') return data.clearances.cases.map((item) => {
    const person = data.employees.find((entry) => entry.id === item.employeeId)
    const outstanding = data.workflows.allocations.filter((allocation) => allocation.employeeId === item.employeeId && !data.workflows.returns.some((returned) => returned.allocationReference === allocation.reference))
    return { id: item.reference, reference: item.reference, subject: person ? displayName(person) + ' (' + person.employee_number + ')' : 'Unavailable', details: outstanding.length + ' visible outstanding individual asset(s); partial preview does not establish clearance', category: '', location: '', status: 'Readiness unknown', employee: person ? displayName(person) : '', department: person ? departmentName(data, person) : '', date: '', href: '/exit-clearance' }
  })
  if (kind === 'approvals') return data.approvals.requests.map((item) => {
    const asset = item.assetId ? data.assets.assets.find((entry) => entry.id === item.assetId) : undefined
    const receipt = item.receiptId ? data.assets.receipts.find((entry) => entry.id === item.receiptId) : undefined
    return { id: item.reference, reference: item.reference, subject: item.requestType, details: item.description, category: item.requestType, location: asset?.location ?? receipt?.location ?? '', status: 'Illustrative only; no decision recorded', employee: item.employeeId ? employeeLabel(data, item.employeeId) : '', department: '', date: item.requestDate, href: '/approvals' }
  })
  return []
}
