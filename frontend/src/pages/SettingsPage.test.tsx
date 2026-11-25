import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { SettingsPage } from './SettingsPage'
import { mockEmployeeProvider } from '../employees/mockEmployeeProvider'

describe('SettingsPage', () => {
  it('shows configuration preview and all eight sections', async () => {
    render(<SettingsPage />)
    expect(screen.getByRole('heading', { name: 'Settings' })).toBeInTheDocument()
    expect(screen.getByText(/Configuration preview/)).toBeInTheDocument()
    await screen.findByText('Workspace preferences')
    for (const label of ['General', 'Master data', 'Users and permissions', 'Employee synchronization', 'Notifications', 'AI integration', 'Audit and security', 'Backup and recovery']) {
      expect(screen.getByRole('tab', { name: new RegExp(label) })).toBeInTheDocument()
    }
  })

  it('derives read-only master-data previews from shared fictional providers', async () => {
    render(<SettingsPage />)
    fireEvent.click(screen.getByRole('tab', { name: /Master data/ }))
    expect(await screen.findByText('Inventory-owned master data')).toBeInTheDocument()
    expect(screen.getByText('Demo North Store')).toBeInTheDocument()
    expect(screen.getByText('Departments')).toBeInTheDocument()
    expect(screen.getByText('Suppliers')).toBeInTheDocument()
    expect(screen.getByText(/unavailable in this preview/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Manage inventory master data' })).toBeDisabled()
  })

  it('keeps employment master data separate and synchronization disconnected', async () => {
    render(<SettingsPage />)
    fireEvent.click(screen.getByRole('tab', { name: /Employee synchronization/ }))
    expect(await screen.findByText('Proposed one-way source to Inventory AIOS')).toBeInTheDocument()
    expect(screen.getAllByText('Not connected').length).toBeGreaterThan(0)
    expect(screen.getByText('Unavailable; source schema not verified')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Test connection/ })).toBeDisabled()
  })

  it('shows proposed role concepts without inventing users or effective permissions', async () => {
    render(<SettingsPage />)
    fireEvent.click(screen.getByRole('tab', { name: /Users and permissions/ }))
    expect(await screen.findByText('Role and permission concepts')).toBeInTheDocument()
    expect(screen.getByText(/not an active access list/)).toBeInTheDocument()
    expect(screen.getByText(/Application users and employee master records are separate/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Manage users and roles' })).toBeDisabled()
  })

  it('keeps notification, Grok, audit and backup capabilities unavailable', async () => {
    render(<SettingsPage />)
    fireEvent.click(screen.getByRole('tab', { name: /^Notifications/ }))
    expect(await screen.findByText(/Recipients, delivery channels/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: /^AI integration/ }))
    expect(await screen.findByText('Grok (planned; not connected)')).toBeInTheDocument()
    expect(screen.getByText(/No external AI service is called/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: /^Audit and security/ }))
    expect(await screen.findByText(/runtime audit writing and audit viewing are not enabled/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: /^Backup and recovery/ }))
    expect(await screen.findByText(/not a production backup service/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Back up / Restore' })).toBeDisabled()
  })

  it('shows loading and empty provider states explicitly', async () => {
    const pendingProvider = { load: () => new Promise<never>(() => undefined) }
    const pending = render(<SettingsPage assetProvider={pendingProvider} />)
    expect(screen.getAllByRole('status').some((item) => item.textContent?.includes('Loading fictional configuration preview'))).toBe(true)
    pending.unmount()

    const emptyProvider = { load: async () => ({ products: [], assets: [], lots: [], receipts: [] }) }
    render(<SettingsPage assetProvider={emptyProvider} />)
    fireEvent.click(screen.getByRole('tab', { name: /Master data/ }))
    expect(await screen.findByText('No category preview is available.')).toBeInTheDocument()
    expect(screen.getByText('No location preview is available.')).toBeInTheDocument()
  })
  it('makes no backend requests and exposes no credential entry fields', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
    render(<SettingsPage />)
    await screen.findByText('Workspace preferences')
    expect(fetchSpy).not.toHaveBeenCalled()
    expect(screen.queryByLabelText(/api key|password|secret/i)).not.toBeInTheDocument()
    fetchSpy.mockRestore()
  })

  it('supports keyboard section navigation and renders provider failures explicitly', async () => {
    render(<SettingsPage />)
    const general = screen.getByRole('tab', { name: /General/ })
    general.focus()
    fireEvent.keyDown(general, { key: 'ArrowRight' })
    expect(screen.getByRole('tab', { name: /Master data/ })).toHaveFocus()

    const failedProvider = { load: vi.fn().mockRejectedValue(new Error('private provider detail')) }
    render(<SettingsPage assetProvider={failedProvider} employeeProvider={mockEmployeeProvider} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Configuration preview unavailable.')
    expect(screen.queryByText('private provider detail')).not.toBeInTheDocument()
  })
})