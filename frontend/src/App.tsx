import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from './layouts/AppShell'
import { ApprovalsPage } from './pages/ApprovalsPage'
import { AllocationsPage } from './pages/AllocationsPage'
import { AssetsPage } from './pages/AssetsPage'
import { DashboardPage } from './pages/DashboardPage'
import { EmployeesPage } from './pages/EmployeesPage'
import { ExitClearancePage } from './pages/ExitClearancePage'
import { NotFoundPage } from './pages/NotFoundPage'
import { ReportsPage } from './pages/ReportsPage'
import { RepairsPage } from './pages/RepairsPage'
import { ReturnsPage } from './pages/ReturnsPage'
import { SettingsPage } from './pages/SettingsPage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<DashboardPage />} />
          <Route path="assets" element={<AssetsPage />} />
          <Route path="employees" element={<EmployeesPage />} />
          <Route path="exit-clearance" element={<ExitClearancePage />} />
          <Route path="allocations" element={<AllocationsPage />} />
          <Route path="returns" element={<ReturnsPage />} />
          <Route path="repairs" element={<RepairsPage />} />
          <Route path="approvals" element={<ApprovalsPage />} />
          <Route path="reports" element={<ReportsPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}