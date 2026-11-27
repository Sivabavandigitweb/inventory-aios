import { AppShell } from '../layouts/AppShell'
import { useAuth } from './useAuth'

export function AuthenticatedShell() {
  const { session, logout } = useAuth()
  return <AppShell authenticatedUserId={session?.userId} onLogout={logout} basePath="/app" />
}
