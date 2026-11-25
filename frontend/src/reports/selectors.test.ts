import { describe, expect, it } from 'vitest'
import { mockAssetProvider } from '../assets/mockAssetProvider'
import { mockEmployeeProvider } from '../employees/mockEmployeeProvider'
import { mockWorkflowProvider } from '../workflows/mockWorkflowProvider'
import { mockRepairProvider } from '../repairs/mockRepairProvider'
import { mockExitClearanceProvider } from '../exitClearance/mockExitClearanceProvider'
import { mockApprovalNotificationProvider } from '../approvals/mockApprovalNotificationProvider'
import type { ReportData } from './selectors'
import { buildReportRows } from './selectors'

describe('report selectors', () => {
  it('derive category rows from the shared fictional providers and keep quantities per lot', async () => {
    const [assets, employeePage, workflows, repairs, clearances, approvals] = await Promise.all([
      mockAssetProvider.load(),
      mockEmployeeProvider.listEmployees({ offset: 0, limit: 1000 }),
      mockWorkflowProvider.load(),
      mockRepairProvider.load(),
      mockExitClearanceProvider.load(),
      mockApprovalNotificationProvider.load(),
    ])
    const data: ReportData = {
      assets, employees: employeePage.items, workflows, repairs, clearances, approvals,
      departments: mockEmployeeProvider.departments,
    }
    expect(buildReportRows('assets', data)).toHaveLength(12)
    expect(buildReportRows('employee', data)).toHaveLength(12)
    expect(buildReportRows('repairs', data)).toHaveLength(6)
    const stock = buildReportRows('quantity', data)
    expect(stock).toHaveLength(3)
    expect(stock.map(({ details }) => details)).toEqual([
      'Physical 20 - Reserved 4 - Available 16 illustrative whole counts; unit unresolved',
      'Physical 12 - Reserved 2 - Available 10 illustrative whole counts; unit unresolved',
      'Physical 8 - Reserved 0 - Available 8 illustrative whole counts; unit unresolved',
    ])
  })
})