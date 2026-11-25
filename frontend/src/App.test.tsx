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
    expect(screen.getByRole('heading', { name: 'Good morning, Admin' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Assets' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Employees' })).toBeInTheDocument()
  })

  it('navigates to the asset preview from the sidebar', async () => {
    render(<App />)

    fireEvent.click(screen.getByRole('link', { name: 'Assets' }))

    expect(screen.getByRole('heading', { name: 'Assets' })).toBeInTheDocument()
    expect(await screen.findByRole('table', { name: 'Fictional individual asset directory' })).toBeInTheDocument()
  })
})
