import { afterEach, describe, expect, it, vi } from 'vitest'
import { AuthApiError, httpAuthApi } from './authApi'

afterEach(() => vi.unstubAllGlobals())

describe('cookie-based authentication API', () => {
  it('obtains login CSRF evidence and sends credentials only in the protected POST body', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ csrf_token: 'fictional-csrf' }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ authenticated: true, user_id: 'fictional-user', csrf_token: 'session-csrf' }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    const result = await httpAuthApi.login({ username: 'fictional.admin', password: 'fictional-password' })
    expect(result).toEqual({ userId: 'fictional-user', csrfToken: 'session-csrf' })
    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/auth/csrf')
    const loginCall = fetchMock.mock.calls[1]
    expect(loginCall[0]).toBe('/api/v1/auth/login')
    expect(loginCall[1]).toMatchObject({ method: 'POST', credentials: 'include', cache: 'no-store' })
    expect(loginCall[1].headers['X-CSRF-Token']).toBe('fictional-csrf')
    expect(loginCall[1].body).toBe(JSON.stringify({ username: 'fictional.admin', password: 'fictional-password' }))
  })

  it('treats absent sessions as anonymous and service failures as unavailable', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(new Response('', { status: 401 })))
    await expect(httpAuthApi.getSession()).resolves.toBeNull()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(new Response('', { status: 503 })))
    await expect(httpAuthApi.getSession()).rejects.toBeInstanceOf(AuthApiError)
  })

  it('does not claim logout succeeded when the server cannot confirm revocation', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(new Response('', { status: 503 })))
    await expect(httpAuthApi.logout('fictional-csrf')).resolves.toBe(false)
  })
})
