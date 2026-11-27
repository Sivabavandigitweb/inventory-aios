export type AuthenticatedSession = { userId: string; csrfToken: string }
export type LoginCredentials = { username: string; password: string }

export interface AuthApi {
  getSession(): Promise<AuthenticatedSession | null>
  login(credentials: LoginCredentials): Promise<AuthenticatedSession>
  logout(csrfToken: string): Promise<boolean>
}

export class AuthApiError extends Error {
  constructor(readonly status: number) {
    super('Authentication service request failed')
    this.name = 'AuthApiError'
  }
}

type SessionPayload = { authenticated: true; user_id: string; csrf_token: string }
type CsrfPayload = { csrf_token: string }

const API_ROOT = '/api/v1/auth'

async function checkedJson<T>(response: Response): Promise<T> {
  if (!response.ok) throw new AuthApiError(response.status)
  try {
    return await response.json() as T
  } catch {
    throw new AuthApiError(502)
  }
}

export const httpAuthApi: AuthApi = {
  async getSession() {
    const response = await fetch(`${API_ROOT}/session`, {
      method: 'GET', credentials: 'include', cache: 'no-store', headers: { Accept: 'application/json' },
    })
    if (response.status === 401) return null
    const payload = await checkedJson<SessionPayload>(response)
    if (payload.authenticated !== true || typeof payload.user_id !== 'string' || typeof payload.csrf_token !== 'string') {
      throw new AuthApiError(502)
    }
    return { userId: payload.user_id, csrfToken: payload.csrf_token }
  },

  async login(credentials) {
    const csrfResponse = await fetch(`${API_ROOT}/csrf`, {
      method: 'GET', credentials: 'include', cache: 'no-store', headers: { Accept: 'application/json' },
    })
    const csrf = await checkedJson<CsrfPayload>(csrfResponse)
    if (typeof csrf.csrf_token !== 'string' || !csrf.csrf_token) throw new AuthApiError(502)
    const response = await fetch(`${API_ROOT}/login`, {
      method: 'POST', credentials: 'include', cache: 'no-store',
      headers: { Accept: 'application/json', 'Content-Type': 'application/json', 'X-CSRF-Token': csrf.csrf_token },
      body: JSON.stringify(credentials),
    })
    const payload = await checkedJson<SessionPayload>(response)
    if (payload.authenticated !== true || typeof payload.user_id !== 'string' || typeof payload.csrf_token !== 'string') {
      throw new AuthApiError(502)
    }
    return { userId: payload.user_id, csrfToken: payload.csrf_token }
  },

  async logout(csrfToken) {
    const response = await fetch(`${API_ROOT}/logout`, {
      method: 'POST', credentials: 'include', cache: 'no-store',
      headers: { Accept: 'application/json', 'X-CSRF-Token': csrfToken },
    })
    return response.ok
  },
}
