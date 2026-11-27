import { useCallback, useMemo, useState, type ReactNode } from 'react'
import { AuthApiError, httpAuthApi, type AuthApi, type AuthenticatedSession, type LoginCredentials } from './authApi'
import { AuthContext, type AuthContextValue, type AuthStatus } from './context'

export function AuthProvider({ children, api = httpAuthApi }: { children: ReactNode; api?: AuthApi }) {
  const [status, setStatus] = useState<AuthStatus>('idle')
  const [session, setSession] = useState<AuthenticatedSession | null>(null)
  const [failure, setFailure] = useState<AuthContextValue['failure']>(null)

  const refresh = useCallback(async () => {
    setStatus('checking')
    try {
      const result = await api.getSession()
      setSession(result)
      setStatus(result ? 'authenticated' : 'anonymous')
      if (!result) setFailure(null)
    } catch {
      setSession(null)
      setStatus('unavailable')
    }
  }, [api])

  const login = useCallback(async (credentials: LoginCredentials) => {
    setFailure(null)
    setStatus('checking')
    try {
      const result = await api.login(credentials)
      setSession(result)
      setStatus('authenticated')
      return true
    } catch (error) {
      setSession(null)
      if (error instanceof AuthApiError && [400, 401, 403, 422, 429].includes(error.status)) {
        setStatus('anonymous')
        setFailure('credentials')
      } else {
        setStatus('unavailable')
        setFailure('unavailable')
      }
      return false
    }
  }, [api])

  const logout = useCallback(async () => {
    let revoked = false
    if (session) {
      try { revoked = await api.logout(session.csrfToken) } catch { revoked = false }
    }
    setSession(null)
    setStatus(revoked ? 'anonymous' : 'unavailable')
    return revoked
  }, [api, session])

  const value = useMemo(() => ({
    status, session, failure, refresh, login, logout,
    clearFailure: () => setFailure(null),
  }), [status, session, failure, refresh, login, logout])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
