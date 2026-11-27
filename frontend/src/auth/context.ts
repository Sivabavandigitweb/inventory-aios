import { createContext } from 'react'
import type { AuthenticatedSession, LoginCredentials } from './authApi'

export type AuthStatus = 'idle' | 'checking' | 'anonymous' | 'authenticated' | 'unavailable'
export type AuthContextValue = {
  status: AuthStatus
  session: AuthenticatedSession | null
  failure: 'credentials' | 'unavailable' | null
  refresh: () => Promise<void>
  login: (credentials: LoginCredentials) => Promise<boolean>
  logout: () => Promise<boolean>
  clearFailure: () => void
}

export const AuthContext = createContext<AuthContextValue | null>(null)
