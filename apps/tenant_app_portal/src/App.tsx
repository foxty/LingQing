import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import Layout from './components/Layout'
import { Toaster } from './components/ui/sonner'
import { useAuth } from './hooks/useAuth'
import { PERMISSIONS } from '@/lib/permissionRules'
import ArtifactsPage from './pages/ArtifactsPage'
import DashboardPage from './pages/DashboardPage'
import DashboardsPage from './pages/DashboardsPage'
import DataAssetsPage from './pages/DataAssetsPage'
import ApiConnectorsPage from './pages/ApiConnectorsPage'
import ApiConnectorDetailPage from './pages/ApiConnectorDetailPage'
import DataSourcesPage from './pages/DataSourcesPage'
import KnowledgeBasePage from './pages/KnowledgeBasePage'
import LiveAppsPage from './pages/LiveAppsPage'
import LoginPage from './pages/LoginPage'
import ReportPage from './pages/ReportPage'
import ReportsPage from './pages/ReportsPage'
import SearchPage from './pages/SearchPage'
import SettingsPage from './pages/SettingsPage'
import SettingsAbacTab from './pages/SettingsAbacTab'
import SettingsEmbeddingConfigTab from './pages/SettingsEmbeddingConfigTab'
import SettingsLLMConfigTab from './pages/SettingsLLMConfigTab'
import SettingsSubscriptionTab from './pages/SettingsSubscriptionTab'
import SettingsTagsTab from './pages/SettingsTagsTab'
import SettingsUsageTab from './pages/SettingsUsageTab'
import SettingsUsersTab from './pages/SettingsUsersTab'
import SettingsIdentityTab from './pages/SettingsIdentityTab'
import SettingsDocumentSourcesTab from './pages/SettingsDocumentSourcesTab'
import SettingsSystemJobsTab from './pages/SettingsSystemJobsTab'
import SsoCallbackPage from './pages/SsoCallbackPage'
import ScheduledTaskPage from './pages/ScheduledTaskPage'
import ScheduledTasksPage from './pages/ScheduledTasksPage'
import SkillsPage from './pages/SkillsPage'
import AgentsPage from './pages/AgentsPage'
import UserProfilePage from './pages/UserProfilePage'
import WorkbenchPage from './pages/WorkbenchPage'

function ProtectedRoute({
  children,
  withLayout = true,
  permission,
}: {
  children: React.ReactNode
  withLayout?: boolean
  permission?: string
}) {
  const { user, loading, hasPermission } = useAuth()
  const { t } = useTranslation()

  // Wait for auth to finish loading
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <p className="text-sm text-muted-foreground">{t('common.loading')}</p>
      </div>
    )
  }

  if (!user) {
    return <Navigate to="/login" replace />
  }

  // Permission-gated route: redirect to the safe landing instead of rendering
  // a page whose API calls will 403. Dashboards is always reachable (shared
  // artifacts are viewable without the gated permission).
  if (permission && !hasPermission(permission)) {
    return <Navigate to="/artifacts/dashboards" replace />
  }

  return withLayout ? <Layout>{children}</Layout> : <>{children}</>
}

/**
 * Permission-aware default landing. Users with chat.access land on the
 * conversation workbench; everyone else lands on dashboards, which is a
 * safe universal page (shared artifacts are viewable without chat.access).
 * Prevents no-chat roles (e.g. viewer) from being stranded on a 403 dead-end.
 */
function DefaultRedirect() {
  const { hasPermission } = useAuth()
  const to = hasPermission(PERMISSIONS.CHAT_ACCESS) ? '/workbench' : '/artifacts/dashboards'
  return <Navigate to={to} replace />
}

function RedirectWithSearch({ to }: { to: string }) {
  const location = useLocation()
  return <Navigate to={`${to}${location.search}`} replace />
}

function App() {
  return (
    <BrowserRouter>
      <Toaster />
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/login/sso" element={<SsoCallbackPage />} />
        <Route path="/" element={<DefaultRedirect />} />
        <Route path="/chat" element={<DefaultRedirect />} />
        <Route path="/chat/:agentId" element={<DefaultRedirect />} />
        <Route
          path="/workbench"
          element={
            <ProtectedRoute permission={PERMISSIONS.CHAT_ACCESS}>
              <WorkbenchPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/workbench/:threadId"
          element={
            <ProtectedRoute permission={PERMISSIONS.CHAT_ACCESS}>
              <WorkbenchPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/dashboards/:dashboardId"
          element={
            <ProtectedRoute>
              <DashboardPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/dashboards/:dashboardId/embed"
          element={
            <ProtectedRoute withLayout={false}>
              <DashboardPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/knowledge"
          element={
            <ProtectedRoute>
              <KnowledgeBasePage />
            </ProtectedRoute>
          }
        />
        <Route path="/knowledge-base" element={<RedirectWithSearch to="/knowledge" />} />
        <Route
          path="/skills"
          element={
            <ProtectedRoute>
              <SkillsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/agents"
          element={
            <ProtectedRoute>
              <AgentsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/search"
          element={
            <ProtectedRoute>
              <SearchPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/data-sources"
          element={
            <ProtectedRoute>
              <DataSourcesPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/api-connectors"
          element={
            <ProtectedRoute>
              <ApiConnectorsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/api-connectors/:connectorId"
          element={
            <ProtectedRoute>
              <ApiConnectorDetailPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/data-sources/:dataSourceId/assets"
          element={
            <ProtectedRoute>
              <DataAssetsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/artifacts"
          element={
            <ProtectedRoute>
              <ArtifactsPage />
            </ProtectedRoute>
          }
        >
          <Route index element={<Navigate to="reports" replace />} />
          <Route path="reports" element={<ReportsPage />} />
          <Route path="dashboards" element={<DashboardsPage />} />
          <Route path="live-apps" element={<LiveAppsPage />} />
          <Route path="scheduled-tasks" element={<ScheduledTasksPage />} />
        </Route>
        <Route path="/dashboards" element={<Navigate to="/artifacts/dashboards" replace />} />
        <Route path="/reports" element={<Navigate to="/artifacts/reports" replace />} />
        <Route path="/live-apps" element={<Navigate to="/artifacts/live-apps" replace />} />
        <Route path="/scheduled-tasks" element={<RedirectWithSearch to="/artifacts/scheduled-tasks" />} />
        <Route
          path="/scheduled-tasks/:taskId"
          element={
            <ProtectedRoute>
              <ScheduledTaskPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/scheduled-tasks/:taskId/embed"
          element={
            <ProtectedRoute withLayout={false}>
              <ScheduledTaskPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/reports/:reportId"
          element={
            <ProtectedRoute>
              <ReportPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/reports/:reportId/embed"
          element={
            <ProtectedRoute withLayout={false}>
              <ReportPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/profile"
          element={
            <ProtectedRoute>
              <UserProfilePage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/settings"
          element={
            <ProtectedRoute>
              <SettingsPage />
            </ProtectedRoute>
          }
        >
          <Route index element={<Navigate to="models" replace />} />
          <Route path="models" element={<SettingsLLMConfigTab />} />
          <Route path="embedding" element={<SettingsEmbeddingConfigTab />} />
          <Route path="tags" element={<SettingsTagsTab />} />
          <Route path="abac" element={<SettingsAbacTab />} />
          <Route path="identity" element={<SettingsIdentityTab />} />
          <Route
            path="document-sources"
            element={<SettingsDocumentSourcesTab />}
          />
          <Route path="sso" element={<Navigate to="/settings/identity" replace />} />
          <Route path="users" element={<SettingsUsersTab />} />
          <Route path="usage" element={<SettingsUsageTab />} />
          <Route path="system-jobs" element={<SettingsSystemJobsTab />} />
          <Route path="subscription" element={<SettingsSubscriptionTab />} />
        </Route>
        <Route path="*" element={<DefaultRedirect />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
