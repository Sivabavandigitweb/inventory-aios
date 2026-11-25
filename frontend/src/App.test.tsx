import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import App from './App'

beforeEach(() => {
  window.history.pushState({}, '', '/dashboard')
})

describe('Inventory AIOS application shell', () => {
  it('renders the dashboard shell and primary navigation', () => {
    render(<App />)

    expect(screen.getByText('Inventory AIOS')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Inventory dashboard' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Assets' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Employees' })).toBeInTheDocument()
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
