import { useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { navigationItems } from '../components/navigation'

export function AppShell() {
  const [isSidebarOpen, setIsSidebarOpen] = useState(false)
  const location = useLocation()
  const currentPage = navigationItems.find((item) => location.pathname === item.to)

  return (
    <div className="app-shell">
      <button
        className={`sidebar-backdrop ${isSidebarOpen ? 'is-visible' : ''}`}
        aria-label="Close navigation"
        onClick={() => setIsSidebarOpen(false)}
      />
      <aside className={`sidebar ${isSidebarOpen ? 'is-open' : ''}`} aria-label="Primary navigation">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true">IA</div>
          <div>
            <span className="brand-name">Inventory AIOS</span>
            <span className="brand-caption">Asset operations</span>
          </div>
        </div>
        <nav className="nav-list" aria-label="Main modules">
          <span className="nav-section-label">Workspace</span>
          {navigationItems.slice(0, 6).map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end
              className={({ isActive }) => `nav-link ${isActive ? 'is-active' : ''}`}
              onClick={() => setIsSidebarOpen(false)}
            >
              <span className="nav-icon" aria-hidden="true">{item.icon}</span>
              <span>{item.label}</span>
            </NavLink>
          ))}
          <span className="nav-section-label nav-section-spaced">Insights</span>
          {navigationItems.slice(6).map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end
              className={({ isActive }) => `nav-link ${isActive ? 'is-active' : ''}`}
              onClick={() => setIsSidebarOpen(false)}
            >
              <span className="nav-icon" aria-hidden="true">{item.icon}</span>
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <span className="status-dot preview-dot" aria-hidden="true" />
          <span>Preview mode</span>
        </div>
      </aside>

      <div className="main-column">
        <header className="topbar">
          <button className="menu-button" type="button" aria-label="Open navigation" onClick={() => setIsSidebarOpen(true)}>
            <span aria-hidden="true">&#9776;</span>
          </button>
          <div className="breadcrumb" aria-label="Breadcrumb">
            <span>Workspace</span>
            <span aria-hidden="true">/</span>
            <strong>{currentPage?.label ?? 'Dashboard'}</strong>
          </div>
          <div className="topbar-actions">
            <button className="icon-button" type="button" aria-label="Notifications unavailable" title="No notification service is connected" disabled>
              <span aria-hidden="true">&#9825;</span>

            </button>
            <div className="user-menu" aria-label="Preview session">
              <span className="avatar" aria-hidden="true">PV</span>
              <span className="user-copy"><strong>Preview session</strong><small>Authentication not connected</small></span>
            </div>
          </div>
        </header>
        <main id="main-content" className="main-content">
          <Outlet />
        </main>
      </div>
    </div>
  )
}