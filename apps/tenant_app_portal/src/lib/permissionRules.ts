/**
 * Permission Rules & Feature Gating
 *
 * This file centralizes permission-based feature visibility.
 * Use these rules to gate UI elements consistently across the app.
 *
 * Pattern:
 * - Define a rule for each feature (e.g., NAV_DOCUMENTS_VISIBLE)
 * - Use the permission checking functions from useAuth hook
 * - Apply in components: <Can any={[rule1, rule2]}>{children}</Can>
 *
 * Permissions come from the tenant app service and match apps/shared/authz/ta_permissions.py
 *
 * Artifact access model:
 * - Read access is ownership-based (own + shared + artifacts.manage), not permission-gated
 * - *.write permissions gate creation only
 * - artifacts.manage grants viewing/managing all artifacts in the tenant
 */

// ==============================================================================
// Permission constants (match apps/shared/authz/ta_permissions.py)
// ==============================================================================

export const PERMISSIONS = {
  // Tenant
  TENANT_ADMIN: 'tenant.admin',
  TENANT_SETTINGS_READ: 'tenant.settings.read',
  TENANT_SETTINGS_WRITE: 'tenant.settings.write',

  // Users & RBAC
  USERS_MANAGE: 'users.manage',
  RBAC_MANAGE: 'rbac.manage',

  // Auth providers
  AUTH_PROVIDERS_MANAGE: 'auth.providers.manage',

  // Data sources
  DATA_SOURCES_READ: 'data_sources.read',
  DATA_SOURCES_WRITE: 'data_sources.write',

  // Dashboards
  DASHBOARDS_WRITE: 'dashboards.write',
  DASHBOARDS_SQL_EXECUTE: 'dashboards.sql.execute',

  // Chat
  CHAT_ACCESS: 'chat.access',

  // Documents
  DOCUMENTS_READ: 'documents.read',
  DOCUMENTS_WRITE: 'documents.write',
  DOCUMENTS_MANAGE: 'documents.manage',

  // Tags / ABAC
  TAGS_READ: 'tags.read',
  TAGS_MANAGE: 'tags.manage',

  // Audit
  AUDIT_READ: 'audit.read',

  // Live apps
  APPS_WRITE: 'apps.write',

  // Artifacts
  ARTIFACTS_MANAGE: 'artifacts.manage',
  REPORTS_WRITE: 'reports.write',
  SCHEDULED_TASKS_WRITE: 'scheduled_tasks.write',
  API_CONNECTORS_CREATE: 'api_connectors.create',
  API_CONNECTORS_MANAGE: 'api_connectors.manage',

  // Skills
  SKILLS_READ: 'skills.read',
  SKILLS_WRITE: 'skills.write',
  SKILLS_MANAGE: 'skills.manage',

  AGENTS_READ: 'agents.read',
  AGENTS_WRITE: 'agents.write',
  AGENTS_MANAGE: 'agents.manage',
} as const

// ==============================================================================
// Feature Rules (compose permissions into UI features)
// ==============================================================================

/**
 * Rules for sidebar/nav visibility.
 * Artifact pages (dashboards, reports, scheduled tasks, apps) are always visible
 * since users may have items shared with them regardless of creation permission.
 */
export const navRules = {
  showConversationMenu: () => [
    PERMISSIONS.CHAT_ACCESS,
  ],

  showSkillsMenu: () => [
    PERMISSIONS.SKILLS_READ,
    PERMISSIONS.SKILLS_WRITE,
  ],

  showAgentsMenu: () => [
    PERMISSIONS.AGENTS_READ,
    PERMISSIONS.AGENTS_WRITE,
    PERMISSIONS.AGENTS_MANAGE,
  ],

  showDocumentsMenu: () => [
    PERMISSIONS.DOCUMENTS_READ,
    PERMISSIONS.DOCUMENTS_WRITE,
  ],

  showDataSourcesMenu: () => [
    PERMISSIONS.DATA_SOURCES_READ,
    PERMISSIONS.DATA_SOURCES_WRITE,
  ],

  showSettingsMenu: () => [
    PERMISSIONS.TENANT_SETTINGS_READ,
    PERMISSIONS.TENANT_SETTINGS_WRITE,
    PERMISSIONS.RBAC_MANAGE,
    PERMISSIONS.USERS_MANAGE,
    PERMISSIONS.TAGS_MANAGE,
  ],

  showApiConnectorsMenu: () => [
    PERMISSIONS.API_CONNECTORS_CREATE,
    PERMISSIONS.API_CONNECTORS_MANAGE,
  ],
}

/**
 * Rules for action buttons visibility.
 * Creation actions require the *.write permission for that artifact type.
 */
export const actionRules = {
  canReadDocuments: () => [PERMISSIONS.DOCUMENTS_READ],
  canUploadDocument: () => [PERMISSIONS.DOCUMENTS_WRITE],
  canDeleteDocument: () => [PERMISSIONS.DOCUMENTS_WRITE],
  canManageDocumentSources: () => [PERMISSIONS.DOCUMENTS_MANAGE],

  canCreateDataSource: () => [PERMISSIONS.DATA_SOURCES_WRITE],
  canEditDataSource: () => [PERMISSIONS.DATA_SOURCES_WRITE],
  canDeleteDataSource: () => [PERMISSIONS.DATA_SOURCES_WRITE],

  canCreateDashboard: () => [PERMISSIONS.DASHBOARDS_WRITE],
  canDeleteDashboard: () => [PERMISSIONS.DASHBOARDS_WRITE],

  canCreateReport: () => [PERMISSIONS.REPORTS_WRITE],
  canCreateScheduledTask: () => [PERMISSIONS.SCHEDULED_TASKS_WRITE],
  canCreateApp: () => [PERMISSIONS.APPS_WRITE],

  canCreateApiConnector: () => [PERMISSIONS.API_CONNECTORS_CREATE],
  canEditApiConnector: () => [PERMISSIONS.API_CONNECTORS_CREATE, PERMISSIONS.API_CONNECTORS_MANAGE],
  canDeleteApiConnector: () => [PERMISSIONS.API_CONNECTORS_CREATE, PERMISSIONS.API_CONNECTORS_MANAGE],

  canExecuteSQL: () => [PERMISSIONS.DASHBOARDS_SQL_EXECUTE],

  canReadTags: () => [PERMISSIONS.TAGS_READ, PERMISSIONS.TAGS_MANAGE],
  canManageTags: () => [PERMISSIONS.TAGS_MANAGE],

  canUploadSkill: () => [PERMISSIONS.SKILLS_MANAGE],
  canDeleteSkill: () => [PERMISSIONS.SKILLS_MANAGE],

  canCreateAgent: () => [PERMISSIONS.AGENTS_WRITE, PERMISSIONS.AGENTS_MANAGE],

  canManageAllArtifacts: () => [PERMISSIONS.ARTIFACTS_MANAGE],
}

/**
 * Delete/manage ACL on artifacts is owner-only unless the actor has artifacts.manage.
 * Role-level *.write does not grant delete on shared artifacts.
 */
export function canDeleteOwnedArtifact(
  ownerId: number | null | undefined,
  userId: number | null | undefined,
  hasManageAll: boolean,
): boolean {
  if (hasManageAll) {
    return true
  }
  if (ownerId == null || userId == null) {
    return false
  }
  return ownerId === userId
}

/**
 * Rules for route protection.
 * Artifact list/detail access is enforced by the API (own + shared + artifacts.manage).
 * Do not gate UI on chat.access alone; use a broad OR so users without chat can still
 * open shared dashboards, apps, reports, etc. when their role allows.
 */
export const routeRules = {
  canAccessDocuments: () => [
    PERMISSIONS.DOCUMENTS_READ,
    PERMISSIONS.DOCUMENTS_WRITE,
  ],

  canAccessDataSources: () => [
    PERMISSIONS.DATA_SOURCES_READ,
    PERMISSIONS.DATA_SOURCES_WRITE,
  ],

  canAccessArtifacts: () => [
    PERMISSIONS.DATA_SOURCES_READ,
    PERMISSIONS.DATA_SOURCES_WRITE,
    PERMISSIONS.DOCUMENTS_READ,
    PERMISSIONS.DOCUMENTS_WRITE,
    PERMISSIONS.CHAT_ACCESS,
    PERMISSIONS.DASHBOARDS_WRITE,
    PERMISSIONS.DASHBOARDS_SQL_EXECUTE,
    PERMISSIONS.REPORTS_WRITE,
    PERMISSIONS.SCHEDULED_TASKS_WRITE,
    PERMISSIONS.APPS_WRITE,
    PERMISSIONS.ARTIFACTS_MANAGE,
    PERMISSIONS.TAGS_READ,
    PERMISSIONS.TAGS_MANAGE,
  ],

  canAccessSkills: () => [
    PERMISSIONS.SKILLS_READ,
    PERMISSIONS.SKILLS_WRITE,
  ],

  canAccessAgents: () => [
    PERMISSIONS.AGENTS_READ,
    PERMISSIONS.AGENTS_WRITE,
    PERMISSIONS.AGENTS_MANAGE,
  ],

  canAccessAgentFeedback: () => [PERMISSIONS.TENANT_ADMIN, PERMISSIONS.AGENTS_MANAGE],

  canAccessSettings: () => [
    PERMISSIONS.TENANT_SETTINGS_READ,
    PERMISSIONS.RBAC_MANAGE,
    PERMISSIONS.USERS_MANAGE,
    PERMISSIONS.TAGS_READ,
  ],
}
