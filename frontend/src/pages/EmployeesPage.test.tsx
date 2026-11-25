import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { mockEmployeeProvider } from '../employees/mockEmployeeProvider'
import type { EmployeeDirectoryProvider } from '../employees/types'
import { EmployeesPage } from './EmployeesPage'

async function renderReady(provider: EmployeeDirectoryProvider = mockEmployeeProvider) {
  render(<EmployeesPage provider={provider} />)
  return screen.findByRole('table', { name: 'Fictional employee directory' })
}

describe('Employees frontend foundation', () => {
  it('renders the title, summary and explicit fictional mock mode without backend requests', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
    try {
      await renderReady()
      expect(screen.getByRole('heading', { name: 'Employees' })).toBeInTheDocument()
      expect(screen.getByText('Fictional preview data')).toBeInTheDocument()
      expect(screen.getByText(/makes no backend requests/)).toBeInTheDocument()
      const summary = screen.getByRole('region', { name: 'Employee summary' })
      expect(within(summary).getByText('12')).toBeInTheDocument()
      expect(within(summary).getByText('9')).toBeInTheDocument()
      expect(fetchSpy).not.toHaveBeenCalled()
    } finally {
      fetchSpy.mockRestore()
    }
  })

  it('renders the directory with contract fields and fictional records', async () => {
    const table = await renderReady()
    expect(within(table).getByText('Mira Vale')).toBeInTheDocument()
    expect(within(table).getByText('DEMO-001')).toBeInTheDocument()
    expect(within(table).getAllByText('Technology').length).toBeGreaterThan(0)
    expect(within(table).getAllByText('Support').length).toBeGreaterThan(0)
    expect(within(table).getAllByText('Specialist').length).toBeGreaterThan(0)
    expect(within(table).getAllByText('Active').length).toBeGreaterThan(0)
    expect(within(table).getAllByRole('row')).toHaveLength(6)
  })

  it('searches names and codes and returns an empty state for no match', async () => {
    await renderReady()
    const search = screen.getByRole('searchbox', { name: 'Search employees' })
    fireEvent.change(search, { target: { value: 'Mira Vale' } })
    await waitFor(() => expect(screen.getByText('Showing 1–1 of 1 · Page 1 of 1')).toBeInTheDocument())
    expect(screen.queryByText('Noah Reed')).not.toBeInTheDocument()
    fireEvent.change(search, { target: { value: 'DEMO-003' } })
    expect(await screen.findByText('Asha Quinn')).toBeInTheDocument()
    fireEvent.change(search, { target: { value: 'no such employee' } })
    expect(await screen.findByText('No employees found.')).toBeInTheDocument()
  })

  it('filters by department and supported status, then resets pagination', async () => {
    await renderReady()
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    await waitFor(() => expect(screen.getByText('Showing 6–10 of 12 · Page 2 of 3')).toBeInTheDocument())
    fireEvent.change(screen.getByLabelText('Department'), {
      target: { value: mockEmployeeProvider.departments[0].id },
    })
    await waitFor(() => expect(screen.getByText('Showing 1–5 of 5 · Page 1 of 1')).toBeInTheDocument())
    fireEvent.change(screen.getByLabelText('Employment status'), { target: { value: 'inactive' } })
    await waitFor(() => expect(screen.getByText('Showing 1–1 of 1 · Page 1 of 1')).toBeInTheDocument())
    expect(screen.getByText('Ilan Wells')).toBeInTheDocument()
    expect(screen.queryByText('Mira Vale')).not.toBeInTheDocument()
  })

  it('paginates without duplicate rows', async () => {
    await renderReady()
    expect(screen.getByText('DEMO-001')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    await waitFor(() => expect(screen.getByText('DEMO-006')).toBeInTheDocument())
    expect(screen.queryByText('DEMO-001')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Previous' }))
    await waitFor(() => expect(screen.getByText('DEMO-001')).toBeInTheDocument())
  })

  it('opens details, labels future sections honestly, and restores focus on Escape', async () => {
    await renderReady()
    const trigger = screen.getByRole('button', { name: 'View details for Mira Vale' })
    trigger.focus()
    fireEvent.click(trigger)
    const dialog = screen.getByRole('dialog', { name: 'Mira Vale' })
    expect(within(dialog).getByText('DEMO-001')).toBeInTheDocument()
    expect(within(dialog).getByText('Allocated assets')).toBeInTheDocument()
    expect(within(dialog).getByRole('link', { name: 'View fictional allocation examples' })).toHaveAttribute('href', '/allocations?employee=DEMO-001')
    expect(within(dialog).getByText('Unavailable. Allocation records are not connected.')).toBeInTheDocument()
    expect(within(dialog).getByText('Exit and clearance')).toBeInTheDocument()
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })

  it('shows unavailable synchronization and no manual registration controls', async () => {
    await renderReady()
    const sync = screen.getByRole('region', { name: 'Employee synchronization' })
    expect(within(sync).getByText('The authoritative employee source is not yet connected.')).toBeInTheDocument()
    expect(within(sync).getByText('Not connected')).toBeInTheDocument()
    expect(within(sync).getByText('Not available')).toBeInTheDocument()
    expect(within(sync).getByText('Unavailable')).toBeInTheDocument()
    expect(within(sync).getByRole('button', { name: 'Sync Employees (unavailable)' })).toBeDisabled()
    expect(screen.queryByRole('button', { name: /Add Employee/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('dialog', { name: 'Add Employee' })).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/Employee code/)).not.toBeInTheDocument()
  })

  it('shows an explicit loading state', () => {
    const provider: EmployeeDirectoryProvider = {
      ...mockEmployeeProvider,
      listEmployees: () => new Promise(() => {}),
    }
    render(<EmployeesPage provider={provider} />)
    expect(screen.getByText('Loading employee preview…')).toBeInTheDocument()
  })

  it('shows a provider error and does not substitute mock records', async () => {
    const provider: EmployeeDirectoryProvider = {
      ...mockEmployeeProvider,
      listEmployees: async () => { throw new Error('Local preview unavailable') },
    }
    render(<EmployeesPage provider={provider} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Employee preview is unavailable.')
    expect(screen.queryByText('Mira Vale')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })

  it('shows an empty directory without fabricated employee history', async () => {
    const provider: EmployeeDirectoryProvider = {
      ...mockEmployeeProvider,
      listEmployees: async (filters) => ({ items: [], total: 0, limit: filters.limit, offset: filters.offset }),
      getSummary: async () => ({ total: 0, active: 0, inactive: 0, departments: 0 }),
    }
    render(<EmployeesPage provider={provider} />)
    expect(await screen.findByText('No employees found.')).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })
})
