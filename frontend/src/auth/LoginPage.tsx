import { useEffect, useState, type FormEvent } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from './useAuth'
import './auth.css'

export function LoginPage() {
  const { status, failure, refresh, login, clearFailure } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => { void refresh() }, [refresh])
  if (status === 'checking' || status === 'idle') {
    return <main className="auth-page"><p role="status">Checking authentication service…</p></main>
  }
  if (status === 'authenticated') return <Navigate to="/app/dashboard" replace />

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (submitting || !username.trim() || !password) return
    setSubmitting(true)
    const accepted = await login({ username, password })
    setPassword('')
    setSubmitting(false)
    if (accepted) {
      const requested = new URLSearchParams(location.search).get('returnTo')
      navigate(requested?.startsWith('/app/') ? requested : '/app/dashboard', { replace: true })
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-card" aria-labelledby="login-heading">
        <Link className="auth-brand" to="/preview" aria-label="Inventory AIOS preview">IA</Link>
        <p className="auth-eyebrow">Inventory AIOS administration</p>
        <h1 id="login-heading">Sign in</h1>
        <p className="auth-description">Use your individually assigned Inventory AIOS account.</p>
        {failure === 'credentials' && <p className="auth-alert" role="alert">The username or password could not be verified.</p>}
        {(status === 'unavailable' || failure === 'unavailable') && <p className="auth-alert" role="alert">Authentication is temporarily unavailable. Please try again later.</p>}
        <form onSubmit={submit} noValidate>
          <label htmlFor="auth-username">Username</label>
          <input id="auth-username" name="username" autoComplete="username" required maxLength={100} value={username} onChange={(event) => { setUsername(event.target.value); clearFailure() }} />
          <label htmlFor="auth-password">Password</label>
          <div className="password-field">
            <input id="auth-password" name="password" type={showPassword ? 'text' : 'password'} autoComplete="current-password" required value={password} onChange={(event) => { setPassword(event.target.value); clearFailure() }} />
            <button type="button" className="password-toggle" onClick={() => setShowPassword((value) => !value)} aria-label={showPassword ? 'Hide password' : 'Show password'}>{showPassword ? 'Hide' : 'Show'}</button>
          </div>
          <button className="auth-submit" type="submit" disabled={submitting || !username.trim() || !password}>
            {submitting ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
        <p className="auth-note">Account registration and password recovery are handled through approved company procedures.</p>
        <Link className="preview-link" to="/preview">Open non-operational previews</Link>
      </section>
    </main>
  )
}
