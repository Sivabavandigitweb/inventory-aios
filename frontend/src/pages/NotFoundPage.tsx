import { Link } from 'react-router-dom'

export function NotFoundPage() {
  return <section className="not-found"><p className="eyebrow">404 error</p><h1>Page not found</h1><p>The workspace page you requested does not exist.</p><Link className="button button-primary" to="/dashboard">Return to dashboard</Link></section>
}