import { useEffect } from 'react'
import { Link, Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from './useAuth'

export function ProtectedWorkspace() {
  const { status, refresh } = useAuth()
  const location = useLocation()
  useEffect(() => { void refresh() }, [refresh])
  useEffect(() => {
    const onFocus = () => { void refresh() }
    window.addEventListener('focus', onFocus)
    const timer = window.setInterval(onFocus, 60_000)
    return () => {
      window.removeEventListener('focus', onFocus)
      window.clearInterval(timer)
    }
  }, [refresh])

  if (status === 'idle' || status === 'checking') return <main className="auth-page"><p role="status">Restoring your Inventory AIOS session…</p></main>
  if (status === 'unavailable') return <main className="auth-page"><section className="auth-card"><h1>Authentication unavailable</h1><p role="alert">The authentication service could not confirm your session. Protected pages remain unavailable.</p><button className="auth-submit" onClick={() => void refresh()}>Try again</button><Link className="preview-link" to="/preview">Open non-operational previews</Link></section></main>
  if (status !== 'authenticated') return <Navigate to={`/login?returnTo=${encodeURIComponent(location.pathname)}`} replace />
  return <Outlet />
}
