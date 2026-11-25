import { useEffect, useRef, type ReactNode } from 'react'

type EmployeeDialogProps = {
  title: string
  onClose: () => void
  children: ReactNode
}

export function EmployeeDialog({ title, onClose, children }: EmployeeDialogProps) {
  const dialogRef = useRef<HTMLDivElement>(null)
  const onCloseRef = useRef(onClose)
  onCloseRef.current = onClose
  const titleId = 'employee-dialog-title'

  useEffect(() => {
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const dialog = dialogRef.current
    const first = dialog?.querySelector<HTMLElement>('[data-initial-focus]')
    ;(first ?? dialog?.querySelector<HTMLElement>('button'))?.focus()

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        event.preventDefault()
        onCloseRef.current()
      }
      if (event.key !== 'Tab' || !dialog) return
      const focusable = [...dialog.querySelectorAll<HTMLElement>(
        'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href]',
      )]
      if (focusable.length === 0) return
      const firstItem = focusable[0]
      const lastItem = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === firstItem) {
        event.preventDefault()
        lastItem.focus()
      } else if (!event.shiftKey && document.activeElement === lastItem) {
        event.preventDefault()
        firstItem.focus()
      }
    }

    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      previous?.focus()
    }
  }, [])

  return (
    <div className="employee-dialog-backdrop">
      <div ref={dialogRef} className="employee-dialog" role="dialog" aria-modal="true" aria-labelledby={titleId}>
        <div className="employee-dialog-heading">
          <h2 id={titleId}>{title}</h2>
          <button type="button" className="employee-close" aria-label="Close panel" onClick={onClose}>×</button>
        </div>
        {children}
      </div>
    </div>
  )
}
