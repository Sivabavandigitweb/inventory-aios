import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mockAssetProvider } from '../assets/mockAssetProvider'
import { mockEmployeeProvider } from '../employees/mockEmployeeProvider'
import { mockWorkflowProvider } from '../workflows/mockWorkflowProvider'
import { validateWorkflowBundle } from '../workflows/useWorkflowPreview'
import type { WorkflowPreviewProvider } from '../workflows/types'
import { AllocationsPage } from './AllocationsPage'

beforeEach(() => { window.history.pushState({}, '', '/allocations') })
async function allocationsReady() {
  render(<AllocationsPage />)
  return screen.findByRole('table', { name: 'Fictional allocation directory' })
}

describe('fictional workflow references', () => {
  it('links allocations and returns to shared-provider records without conflicting custody', async () => {
    const assets = await mockAssetProvider.load()
    const employees = (await mockEmployeeProvider.listEmployees({ offset: 0, limit: 1000 })).items
    const workflow = await mockWorkflowProvider.load()
    const bundle = { assets, employees, workflow }
    expect(() => validateWorkflowBundle(bundle)).not.toThrow()
    expect(workflow.allocations).toHaveLength(8)
    expect(workflow.returns).toHaveLength(6)
    for (const allocation of workflow.allocations) {
      expect(employees.some((item) => item.id === allocation.employeeId)).toBe(true)
      expect(assets.assets.some((item) => item.id === allocation.assetId)).toBe(true)
    }
    for (const item of workflow.returns) {
      expect(workflow.allocations.some((allocation) => allocation.reference === item.allocationReference)).toBe(true)
    }
    const current = workflow.allocations.filter((item) => !workflow.returns.some((returned) => returned.allocationReference === item.reference))
    expect(current.map((item) => item.assetId)).toEqual(['asset-2', 'asset-7'])
    expect(new Set(current.map((item) => item.assetId)).size).toBe(current.length)
  })

  it('rejects missing references and overlapping fictional custody', async () => {
    const assets = await mockAssetProvider.load()
    const employees = (await mockEmployeeProvider.listEmployees({ offset: 0, limit: 1000 })).items
    const workflow = await mockWorkflowProvider.load()
    const first = workflow.allocations[0]
    expect(() => validateWorkflowBundle({ assets, employees, workflow: {
      ...workflow, allocations: [{ ...first, employeeId: 'missing' }, ...workflow.allocations.slice(1)],
    } })).toThrow('Invalid fictional workflow references')
    expect(() => validateWorkflowBundle({ assets, employees, workflow: {
      ...workflow, allocations: [...workflow.allocations, { ...first, reference: 'DEMO-DUPLICATE' }],
    } })).toThrow('Conflicting fictional custody')
  })
})

describe('Allocation Management preview', () => {
  it('renders fictional partial records and calculated summaries without backend requests', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
    try {
      const table = await allocationsReady()
      expect(screen.getByRole('heading', { name: 'Allocations' })).toBeInTheDocument()
      expect(screen.getByText('Fictional preview data')).toBeInTheDocument()
      expect(within(table).getByText('DEMO-ALLOC-001')).toBeInTheDocument()
      const summary = screen.getByRole('region', { name: 'Allocation preview summary' })
      expect(within(summary).getAllByText('8')).toHaveLength(2)
      expect(within(summary).getByText('2')).toBeInTheDocument()
      expect(within(summary).getByText('6')).toBeInTheDocument()
      expect(fetchSpy).not.toHaveBeenCalled()
    } finally { fetchSpy.mockRestore() }
  })

  it('searches, filters by department and custody view, and paginates', async () => {
    await allocationsReady()
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(screen.getByText('DEMO-ALLOC-006')).toBeInTheDocument()
    fireEvent.change(screen.getByRole('searchbox', { name: 'Search allocations' }), { target: { value: 'DEMO-ASSET-001' } })
    expect(screen.getByText('Showing 1–2 of 2 · Page 1 of 1')).toBeInTheDocument()
    fireEvent.change(screen.getByRole('searchbox', { name: 'Search allocations' }), { target: { value: '' } })
    fireEvent.change(screen.getByLabelText('Department'), { target: { value: mockEmployeeProvider.departments[0].id } })
    expect(screen.getByText('Showing 1–4 of 4 · Page 1 of 1')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Preview view'), { target: { value: 'current' } })
    expect(screen.getByText('Showing 1–1 of 1 · Page 1 of 1')).toBeInTheDocument()
  })

  it('shows details, linked fictional return and accessible close', async () => {
    await allocationsReady()
    const trigger = screen.getByRole('button', { name: 'View allocation DEMO-ALLOC-003' })
    trigger.focus()
    fireEvent.click(trigger)
    const dialog = screen.getByRole('dialog', { name: 'DEMO-ALLOC-003' })
    expect(within(dialog).getByText('Demo Officer')).toBeInTheDocument()
    expect(within(dialog).getByRole('link', { name: 'View linked fictional return' })).toHaveAttribute('href', '/returns?allocation=DEMO-ALLOC-003')
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })

  it('allows fictional employee and asset selection but disables allocation submission', async () => {
    await allocationsReady()
    fireEvent.click(screen.getByRole('button', { name: 'New Allocation preview' }))
    const dialog = screen.getByRole('dialog', { name: 'New Allocation preview' })
    fireEvent.change(within(dialog).getByRole('searchbox', { name: 'Search employees' }), { target: { value: 'Mira' } })
    expect(within(dialog).getByRole('option', { name: /Mira Vale/ })).toBeInTheDocument()
    fireEvent.change(within(dialog).getByLabelText('Select fictional employee'), { target: { value: '10000000-0000-4000-8000-000000000001' } })
    fireEvent.change(within(dialog).getByRole('searchbox', { name: 'Search individual assets' }), { target: { value: 'DEMO-ASSET-001' } })
    fireEvent.change(within(dialog).getByLabelText('Select fictional asset'), { target: { value: 'asset-1' } })
    expect(within(dialog).getByText(/Selection is not eligibility approval/)).toBeInTheDocument()
    expect(within(dialog).getByLabelText('Allocation date')).toBeInTheDocument()
    expect(within(dialog).getByLabelText('Assigned by')).toBeInTheDocument()
    expect(within(dialog).getByRole('button', { name: 'Submit allocation (unavailable)' })).toBeDisabled()
    expect(screen.getByText('DEMO-ALLOC-001')).toBeInTheDocument()
  })

  it('shows loading, empty and error states without fallback', async () => {
    const pending: WorkflowPreviewProvider = { load: () => new Promise(() => {}) }
    const loading = render(<AllocationsPage workflowProvider={pending} />)
    expect(screen.getByText('Loading allocation preview…')).toBeInTheDocument()
    loading.unmount()
    const empty: WorkflowPreviewProvider = { load: async () => ({ allocations: [], returns: [] }) }
    const noData = render(<AllocationsPage workflowProvider={empty} />)
    expect(await screen.findByText('No allocation examples found.')).toBeInTheDocument()
    noData.unmount()
    const failed: WorkflowPreviewProvider = { load: async () => { throw new Error('local failure') } }
    render(<AllocationsPage workflowProvider={failed} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Allocation preview is unavailable.')
    expect(screen.queryByText('DEMO-ALLOC-001')).not.toBeInTheDocument()
  })
})
