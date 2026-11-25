import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import App from './App'

beforeEach(() => {
  window.history.pushState({}, '', '/dashboard')
})

describe('Inventory AIOS application shell', () => {
  it('renders the dashboard shell and primary navigation', async () => {
    render(<App />)

    expect(screen.getByText('Inventory AIOS')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Inventory dashboard' })).toBeInTheDocument()
    await screen.findByRole('region', { name: 'Inventory summary' })
    expect(screen.getByRole('link', { name: 'Assets' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Employees' })).toBeInTheDocument()
    expect(screen.getByText('Preview session')).toBeInTheDocument()
    expect(screen.getByText('Authentication not connected')).toBeInTheDocument()
    expect(screen.getByText('Preview mode')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Notifications unavailable' })).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'View notifications' })).not.toBeInTheDocument()
  })

  it('renders every module on direct route access and marks the active navigation item', async () => {
    const routes = [
      ['/dashboard', 'Dashboard', 'Inventory dashboard'], ['/assets', 'Assets', 'Assets'],
      ['/employees', 'Employees', 'Employees'], ['/exit-clearance', 'Exit Clearance', 'Exit Clearance'],
      ['/allocations', 'Allocations', 'Allocations'], ['/returns', 'Returns', 'Returns'],
      ['/repairs', 'Repairs', 'Repairs'], ['/approvals', 'Approvals', 'Approvals and Notifications'],
      ['/reports', 'Reports', 'Reports and Analytics'], ['/settings', 'Settings', 'Settings'],
    ] as const
    for (const [path, label, heading] of routes) {
      window.history.pushState({}, '', path)
      const view = render(<App />)
      expect(await screen.findByRole('heading', { name: heading })).toBeInTheDocument()
      expect(screen.getByRole('link', { name: label })).toHaveClass('is-active')
      view.unmount()
    }
  })

  it('redirects the default route to dashboard and handles invalid routes', async () => {
    window.history.pushState({}, '', '/')
    const dashboard = render(<App />)
    expect(await screen.findByRole('region', { name: 'Inventory summary' })).toBeInTheDocument()
    dashboard.unmount()
    window.history.pushState({}, '', '/not-a-route')
    render(<App />)
    expect(await screen.findByRole('heading', { name: 'Page not found' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Return to dashboard' })).toHaveAttribute('href', '/dashboard')
    expect(screen.getByRole('link', { name: 'Dashboard' })).not.toHaveClass('is-active')
  })

  it('follows browser back and forward through application routes', async () => {
    window.history.pushState({}, '', '/dashboard')
    render(<App />)
    await screen.findByRole('region', { name: 'Inventory summary' })
    fireEvent.click(screen.getByRole('link', { name: 'Employees' }))
    expect(await screen.findByRole('heading', { name: 'Employees' })).toBeInTheDocument()
    window.history.back()
    expect(await screen.findByRole('heading', { name: 'Inventory dashboard' })).toBeInTheDocument()
    window.history.forward()
    expect(await screen.findByRole('heading', { name: 'Employees' })).toBeInTheDocument()
  })
  it('opens the requested asset section from dashboard quick navigation', async () => {
    render(<App />)
    const link = await screen.findByRole('link', { name: /Quantity inventory/ })
    fireEvent.click(link)
    expect(await screen.findByRole('table', { name: 'Fictional quantity inventory' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Quantity inventory' })).toHaveAttribute('aria-selected', 'true')
  })

  it('defaults to individual assets for an unknown section parameter', async () => {
    window.history.pushState({}, '', '/assets?section=unexpected')
    render(<App />)
    expect(await screen.findByRole('table', { name: 'Fictional individual asset directory' })).toBeInTheDocument()
  })
  it('navigates to the asset preview from the sidebar', async () => {
    render(<App />)

    fireEvent.click(screen.getByRole('link', { name: 'Assets' }))

    expect(screen.getByRole('heading', { name: 'Assets' })).toBeInTheDocument()
    expect(await screen.findByRole('table', { name: 'Fictional individual asset directory' })).toBeInTheDocument()
  })

  it('navigates to Exit Clearance from the sidebar', async () => {
    render(<App />)
    const link = screen.getByRole('link', { name: 'Exit Clearance' })
    expect(link).toHaveAttribute('href', '/exit-clearance')
    fireEvent.click(link)
    expect(await screen.findByRole('table', { name: 'Fictional employee clearance directory' })).toBeInTheDocument()
  })})
