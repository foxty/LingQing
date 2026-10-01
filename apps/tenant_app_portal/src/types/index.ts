// ============================================================================
// Frontend Types (camelCase - for internal use)
// ============================================================================

export interface User {
  id: number // User ID from database
  username: string
  role: 'admin' | 'member' | 'viewer'
  tenantId: number // Changed from string to number (database ID)
  tenantName: string // Tenant display name
}

export interface Message {
  role: 'human' | 'ai' | 'tool' | 'system' // Aligned with LangChain's standard naming
  content: string
  timestamp?: string
  tool_calls?: Array<{
    // LangChain parsed format (stored in dedicated field)
    id: string
    name: string
    args: Record<string, any>
    type?: string
  }>
  tool_call_id?: string // For tool messages (results)
  session_id?: string // For linking to observability metrics
  metrics?: SessionMetrics | ToolCallMetrics // Loaded metrics (session-level for AI, tool-level for tool messages)
  additional_kwargs?: {
    hitl?: HitlPayload
    [key: string]: any
  } // Provider-specific extras
  message_metadata?: {
    // System metadata (NOT sent to LLM)
    visibility?: 'internal' | 'public'
    capability_id?: string
    capability_name?: string
    sub_agent_id?: string // ID of the sub-agent that generated this message
    context_resources?: ContextResource[]
    [key: string]: any
  }
  artifact_id?: number // Optional artifact ID (ThreadArtifact.id) for context
  artifact?: Artifact // Optional resolved artifact for display
}

export interface HitlPayload {
  type?: 'approval_request' | 'approval_result'
  proposal_id: string
  version?: number
  status?: 'pending' | 'approved' | 'rejected' | 'expired' | 'executed' | 'cancelled'
  title?: string
  summary?: string
  risk_level?: string
  tool_name?: string
  args_preview?: Record<string, any>
  actions?: string[]
  expires_at?: string
}

export interface SessionMetrics {
  session_id: string
  total_tokens: {
    input_tokens: number
    output_tokens: number
    total_tokens: number
  }
  duration_ms: number
  llm_call_count: number
  tool_call_count: number
  start_time: string
  end_time: string
  model_usage?: Record<string, { calls: number; tokens: number }>
}

export interface ToolCallMetrics {
  tool_call_id: string
  tool_name: string
  status: 'success' | 'error'
  duration_ms: number
  input_size?: number
  output_size?: number
  start_time: string
  end_time: string
  error_message?: string
}

export type DocumentStatus = 'processing' | 'active' | 'failed' | 'deleted'

export type VectorStatus =
  | 'pending'
  | 'indexing'
  | 'indexed'
  | 'stale'
  | 'failed'
  | 'permanent_failed'

export type DocumentIntakeSource = 'upload' | 'drive_sync'

export interface Document {
  id: number
  filename: string
  filePath: string
  uploadDate: string
  fileSize: number
  tenantId: number
  status?: DocumentStatus
  ownerUsername?: string
  fileHash?: string
  vectorStatus?: VectorStatus
  lastVectorSyncedAt?: string
  lastVectorSyncError?: string
  sourceParser?: string
  parsedAt?: string
  parseError?: string
  updatedAt?: string
  intakeSource?: DocumentIntakeSource
  externalFileId?: string
}

export interface Agent {
  agentId: number
  name: string
  description: string
  tags: string[]
  exampleQuestions: string[]
}

export interface Stats {
  totalDocuments: number
  activeAgents: number
}

export interface ChatThread {
  id: string
  tenantId: number
  userId: number
  agentId: number
  title: string | null
  messageCount: number
  createdAt: string
  updatedAt: string
}

// ============================================================================
// API Types (snake_case - matches backend API)
// ============================================================================

export interface ApiUser {
  id: number // User ID from database
  username: string
  role: 'admin' | 'member' | 'viewer'
  tenant_id: number // Changed from string to number (database ID)
  tenant_name: string // Tenant display name
  timezone_iana?: string | null
}

export interface ApiLoginRequest {
  username: string // Format: username@tenant-slug (e.g., admin@demo)
  password: string
}

export interface ApiLoginResponse {
  access_token: string
  token_type: string
  user: ApiUser
}

export interface ApiChatRequest {
  tenant_id: number
  agent_id: number
  message: Message
  stream?: boolean
  username?: string
  config?: Record<string, any>
}

export interface ApiChatResponse {
  response: Message
  agent_id: number
  tenant_id: number
}

export interface ApiDocument {
  id: number
  collection_id: number
  filename: string
  file_url: string
  upload_date: string
  file_size: number
  tenant_id: number
  status?: DocumentStatus
  owner_username?: string
  file_hash?: string
  vector_status?: VectorStatus | null
  last_vector_synced_at?: string | null
  last_vector_sync_error?: string | null
  source_parser?: string | null
  parsed_at?: string | null
  parse_error?: string | null
  updated_at?: string
  intake_source?: DocumentIntakeSource
  external_file_id?: string | null
}

export interface ApiAgent {
  id: number
  name: string
  description: string
  tags: string[]
  example_questions: string[]
}

// ============================================================================
// Type Converters (API snake_case ↔ Frontend camelCase)
// ============================================================================

export const convertApiUserToUser = (apiUser: ApiUser): User => ({
  id: apiUser.id,
  username: apiUser.username,
  role: apiUser.role,
  tenantId: apiUser.tenant_id,
  tenantName: apiUser.tenant_name,
})

export const convertApiDocumentToDocument = (apiDoc: ApiDocument): Document => ({
  id: apiDoc.id,
  filename: apiDoc.filename,
  filePath: apiDoc.file_url,
  uploadDate: apiDoc.upload_date,
  fileSize: apiDoc.file_size,
  tenantId: apiDoc.tenant_id,
  ownerUsername: apiDoc.owner_username,
  fileHash: apiDoc.file_hash,
  status: apiDoc.status,
  vectorStatus: apiDoc.vector_status ?? undefined,
  lastVectorSyncedAt: apiDoc.last_vector_synced_at ?? undefined,
  lastVectorSyncError: apiDoc.last_vector_sync_error ?? undefined,
  sourceParser: apiDoc.source_parser ?? undefined,
  parsedAt: apiDoc.parsed_at ?? undefined,
  parseError: apiDoc.parse_error ?? undefined,
  updatedAt: apiDoc.updated_at,
  intakeSource: apiDoc.intake_source ?? 'upload',
  externalFileId: apiDoc.external_file_id ?? undefined,
})

export const convertApiAgentToAgent = (apiAgent: ApiAgent): Agent => ({
  agentId: apiAgent.id,
  name: apiAgent.name,
  description: apiAgent.description,
  tags: apiAgent.tags,
  exampleQuestions: apiAgent.example_questions,
})

// API types for threads
export interface ApiChatThread {
  id: string
  tenant_id: number
  user_id: number
  agent_id: number
  title: string | null
  message_count: number
  created_at: string
  updated_at: string
}

export const convertApiThreadToThread = (apiThread: ApiChatThread): ChatThread => ({
  id: apiThread.id,
  tenantId: apiThread.tenant_id,
  userId: apiThread.user_id,
  agentId: apiThread.agent_id,
  title: apiThread.title,
  messageCount: apiThread.message_count,
  createdAt: apiThread.created_at,
  updatedAt: apiThread.updated_at,
})

/**
 * Artifact type for both streaming and API responses
 * Represents artifacts created within a thread (Dashboard, Chart, Report, etc.)
 */
export interface Artifact {
  type: 'artifact'
  artifact_type: 'dashboard' | 'report' | 'scheduled_task' | 'iframe' | string
  id: number // ThreadArtifact record ID
  resource_id?: number
  url?: string | null
  title: string
  metadata?: Record<string, any>
  created_at?: string // Optional, included in API responses
  owner_username?: string | null
  is_owner?: boolean
  share_permission?: 'read' | 'write' | null
}

// ============================================================================
// Skill Types
// ============================================================================

export interface ApiSkill {
  name: string
  type: SkillType
  description: string
  enabled: boolean
  env_var_keys: string[]
  created_by: string
  created_at: string
  updated_at: string
}

export const SkillType = {
  BUILTIN: 'builtin',
  TENANT: 'tenant',
  PERSONAL: 'personal',
} as const

export type SkillType = (typeof SkillType)[keyof typeof SkillType]

export interface Skill {
  name: string
  type: SkillType
  description: string
  enabled: boolean
  envVarKeys: string[]
  createdBy: string
  createdAt: string
  updatedAt: string
}

export function convertApiSkillToSkill(api: ApiSkill): Skill {
  return {
    name: api.name,
    type: api.type,
    description: api.description,
    enabled: api.enabled,
    envVarKeys: api.env_var_keys,
    createdBy: api.created_by,
    createdAt: api.created_at,
    updatedAt: api.updated_at,
  }
}

/**
 * Unified context resource type for @mention picker.
 * Represents any resource that can be attached to a chat message as context.
 */
export interface ContextResource {
  resource_type: 'document' | 'dashboard' | 'report' | 'scheduled_task' | 'app' | 'asset'
  resource_id: number
  title: string
  subtitle?: string | null
}
