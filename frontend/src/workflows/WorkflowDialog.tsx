import { useEffect, useRef, type ReactNode } from 'react'

export function WorkflowDialog({ title, onClose, children }: {
  title: string; onClose: () => void; children: ReactNode
}) {
  const ref = useRef<HTMLDivElement>(null)
  const closeRef = useRef(onClose)
  closeRef.current = onClose
  useEffect(() => {
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const dialog = ref.current
    dialog?.querySelector<HTMLElement>('button')?.focus()
    function keydown(event: KeyboardEvent) {
      if (event.key === 'Escape') { event.preventDefault(); closeRef.current(); return }
      if (event.key !== 'Tab' || !dialog) return
      const controls = [...dialog.querySelectorAll<HTMLElement>('button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href]')]
      if (!controls.length) return
      if (event.shiftKey && document.activeElement === controls[0]) {
        event.preventDefault()
        controls[controls.length - 1].focus()
      } else if (!event.shiftKey && document.activeElement === controls[controls.length - 1]) {
        event.preventDefault()
        controls[0].focus()
      }
    }
    document.addEventListener('keydown', keydown)
    return () => { document.removeEventListener('keydown', keydown); previous?.focus() }
  }, [])
  return <div className="workflow-backdrop">
    <div ref={ref} className="workflow-dialog" role="dialog" aria-modal="true" aria-label={title}>
      <div className="workflow-dialog-heading"><h2>{title}</h2><button type="button" className="workflow-close" aria-label="Close panel" onClick={onClose}>×</button></div>
      {children}
    </div>
  </div>
}
