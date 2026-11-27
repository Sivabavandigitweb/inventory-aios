import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AuthContext } from '../auth/context'
import { OperationalLifecyclePage } from './OperationalLifecyclePage'

afterEach(() => vi.unstubAllGlobals())

function renderPage(kind: 'disposals' | 'repairs' = 'disposals') {
  return render(<AuthContext.Provider value={{
    status: 'authenticated', session: { userId: 'fictional-user', csrfToken: 'fictional-csrf' },
    failure: null, refresh: vi.fn(async () => {}), login: vi.fn(async () => true),
    logout: vi.fn(async () => true), clearFailure: vi.fn(),
  }}><OperationalLifecyclePage kind={kind} /></AuthContext.Provider>)
}

describe('authenticated lifecycle workflow page', () => {
  it('shows unavailable operational data without substituting preview records', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', { status: 503 })))
    renderPage()
    expect(await screen.findByRole('alert')).toHaveTextContent('No preview records were substituted')
    expect(screen.queryByText(/TEST|fictional record/i)).not.toBeInTheDocument()
  })

  it('reports confirmed request success only after the API returns success', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify([]), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: 'fictional-request', status: 'pending_approval' }), { status: 201 }))
      .mockResolvedValueOnce(new Response(JSON.stringify([{ id: 'fictional-request', status: 'pending' }]), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    renderPage()
    fireEvent.change(await screen.findByLabelText('Asset ID'), { target: { value: 'fictional-asset-id' } })
    fireEvent.change(screen.getByLabelText('Disposal reason'), { target: { value: 'obsolete' } })
    fireEvent.click(screen.getByRole('button', { name: 'Submit request' }))
    expect(await screen.findByRole('status')).toHaveTextContent('awaiting an explicit approval decision')
    expect(fetchMock.mock.calls[1][1].headers['X-CSRF-Token']).toBe('fictional-csrf')
    expect(fetchMock.mock.calls[1][1].headers['Idempotency-Key']).toBeTruthy()
    expect(JSON.parse(fetchMock.mock.calls[1][1].body).reason_code).toBe('obsolete')
  })

  it('offers only management-approved repair currency codes', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify([{ id: 'fictional-repair', status: 'in_progress' }]), { status: 200 })))
    renderPage('repairs')
    expect(await screen.findByLabelText('Currency')).toHaveTextContent('LKR')
    expect(screen.getByLabelText('Currency')).toHaveTextContent('GBP')
    expect(screen.getByLabelText('Currency')).toHaveTextContent('USD')
    expect(screen.getByLabelText('Currency')).toHaveTextContent('EUR')
    expect(screen.getByLabelText('Currency')).not.toHaveTextContent('JPY')
  })
})
