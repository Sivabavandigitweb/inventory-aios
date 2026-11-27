import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './auth/AuthContext'
import type { AuthApi } from './auth/authApi'
import { AuthenticatedShell } from './auth/AuthenticatedShell'
import { apiAssetProvider } from './assets/apiAssetProvider'
import { apiInventoryWriteProvider } from './assets/apiInventoryWriteProvider'
import { apiEmployeeProvider } from './employees/apiEmployeeProvider'
import { LoginPage } from './auth/LoginPage'
import { ProtectedWorkspace } from './auth/ProtectedWorkspace'
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
import { OperationalModuleUnavailable } from './components/OperationalModuleUnavailable'
import { useAuth } from './auth/useAuth'
import { apiTransactionProvider } from './workflows/apiTransactionProvider'
import { OperationalTransactionsPage } from './workflows/OperationalTransactionsPage'
import { OperationalLifecyclePage } from './workflows/OperationalLifecyclePage'
import { OperationalApprovalsPage } from './workflows/OperationalApprovalsPage'

function AuthenticatedAssetsPage() {
  const { session } = useAuth()
  return <AssetsPage provider={apiAssetProvider} writeProvider={apiInventoryWriteProvider} csrfToken={session?.csrfToken ?? ''} />
}

function AuthenticatedTransactionsPage() {
  const { session } = useAuth()
  return <OperationalTransactionsPage api={apiTransactionProvider} csrfToken={session?.csrfToken ?? ''} />
}

function WorkspaceRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
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
        <Route path="preview" element={<Navigate to="/dashboard" replace />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
      <Route path="/app" element={<ProtectedWorkspace />}>
        <Route element={<AuthenticatedShell />}>
          <Route index element={<Navigate to="/app/dashboard" replace />} />
          <Route path="dashboard" element={<OperationalModuleUnavailable module="Dashboard" />} />
          <Route path="assets" element={<AuthenticatedAssetsPage />} />
          <Route path="employees" element={<EmployeesPage provider={apiEmployeeProvider} />} />
          <Route path="exit-clearance" element={<OperationalLifecyclePage kind="exit-clearance" />} />
          <Route path="disposals" element={<OperationalLifecyclePage kind="disposals" />} />
          <Route path="allocations" element={<AuthenticatedTransactionsPage />} />
          <Route path="returns" element={<AuthenticatedTransactionsPage />} />
          <Route path="repairs" element={<OperationalLifecyclePage kind="repairs" />} />
          <Route path="approvals" element={<OperationalApprovalsPage />} />
          <Route path="reports" element={<OperationalModuleUnavailable module="Reports" />} />
          <Route path="settings" element={<OperationalModuleUnavailable module="Settings" />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Route>
    </Routes>
  )
}

export default function App({ authApi }: { authApi?: AuthApi } = {}) {
  return <BrowserRouter><AuthProvider api={authApi}><WorkspaceRoutes /></AuthProvider></BrowserRouter>
}
