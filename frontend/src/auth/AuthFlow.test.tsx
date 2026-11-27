import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import App from '../App'
import { AuthApiError, type AuthApi, type AuthenticatedSession } from './authApi'

const session: AuthenticatedSession = { userId: 'fictional-user-id', csrfToken: 'fictional-csrf-token' }

function fakeApi(overrides: Partial<AuthApi> = {}): AuthApi {
  return {
    getSession: vi.fn().mockResolvedValue(null),
    login: vi.fn().mockResolvedValue(session),
    logout: vi.fn().mockResolvedValue(true),
    ...overrides,
  }
}

describe('authentication route preparation', () => {
  it('redirects protected workspace routes to login without a confirmed session', async () => {
    window.history.pushState({}, '', '/app/dashboard')
    render(<App authApi={fakeApi()} />)
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open non-operational previews' })).toHaveAttribute('href', '/preview')
  })

  it('submits credentials, keeps unavailable modules free of preview records, and supports logout', async () => {
    window.history.pushState({}, '', '/login')
    const api = fakeApi({ getSession: vi.fn().mockResolvedValueOnce(null).mockResolvedValueOnce(session).mockResolvedValue(null) })
    render(<App authApi={api} />)
    fireEvent.change(await screen.findByLabelText('Username'), { target: { value: 'fictional.admin' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'fictional-passphrase' } })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByRole('heading', { name: 'Dashboard' })).toBeInTheDocument()
    expect(api.login).toHaveBeenCalledWith({ username: 'fictional.admin', password: 'fictional-passphrase' })
    expect(await screen.findAllByText('Authenticated session')).toHaveLength(2)
    expect(screen.getByText(/No preview or fictional records are shown/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Sign out' }))
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
    expect(api.logout).toHaveBeenCalledWith(session.csrfToken)
  })

  it('shows a generic credential failure and never renders test failure details', async () => {
    window.history.pushState({}, '', '/login')
    const api = fakeApi({ login: vi.fn().mockRejectedValue(new AuthApiError(401)) })
    render(<App authApi={api} />)
    fireEvent.change(await screen.findByLabelText('Username'), { target: { value: 'fictional.admin' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'not-the-password' } })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('The username or password could not be verified.')
    expect(screen.queryByText('not-the-password')).not.toBeInTheDocument()
  })

  it('keeps protected routes unavailable when session verification fails', async () => {
    window.history.pushState({}, '', '/app/assets')
    const api = fakeApi({ getSession: vi.fn().mockRejectedValue(new AuthApiError(503)) })
    render(<App authApi={api} />)
    expect(await screen.findByRole('heading', { name: 'Authentication unavailable' })).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByRole('heading', { name: 'Assets' })).not.toBeInTheDocument())
  })

  it('returns to login when a later session check reports expiry', async () => {
    window.history.pushState({}, '', '/app/dashboard')
    const api = fakeApi({ getSession: vi.fn().mockResolvedValueOnce(session).mockResolvedValueOnce(null) })
    render(<App authApi={api} />)
    expect(await screen.findByRole('heading', { name: 'Dashboard' })).toBeInTheDocument()
    window.dispatchEvent(new Event('focus'))
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
  })

  it('clears local access after uncertain logout without reporting server revocation success', async () => {
    window.history.pushState({}, '', '/login')
    const api = fakeApi({
      getSession: vi.fn().mockResolvedValueOnce(null).mockResolvedValueOnce(session),
      logout: vi.fn().mockResolvedValue(false),
    })
    render(<App authApi={api} />)
    fireEvent.change(await screen.findByLabelText('Username'), { target: { value: 'fictional.admin' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'fictional-passphrase' } })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    await screen.findByRole('heading', { name: 'Dashboard' })
    fireEvent.click(screen.getByRole('button', { name: 'Sign out' }))
    expect(await screen.findByRole('heading', { name: 'Authentication unavailable' })).toBeInTheDocument()
    expect(api.logout).toHaveBeenCalledWith(session.csrfToken)
  })

  it('offers an accessible password visibility toggle', async () => {
    window.history.pushState({}, '', '/login')
    render(<App authApi={fakeApi()} />)
    const password = await screen.findByLabelText('Password')
    expect(password).toHaveAttribute('type', 'password')
    fireEvent.click(screen.getByRole('button', { name: 'Show password' }))
    expect(password).toHaveAttribute('type', 'text')
  })
})
