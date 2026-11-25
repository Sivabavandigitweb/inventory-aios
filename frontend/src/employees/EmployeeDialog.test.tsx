import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { EmployeeDialog } from './EmployeeDialog'

describe('Employee details dialog', () => {
  it('moves focus into the dialog and closes on Escape', () => {
    const onClose = vi.fn()
    render(
      <EmployeeDialog title="Fictional employee" onClose={onClose}>
        <p>Preview only</p>
      </EmployeeDialog>,
    )

    expect(screen.getByRole('dialog', { name: 'Fictional employee' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Close panel' })).toHaveFocus()
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledOnce()
  })
})