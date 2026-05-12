import api from './api'

// ============================================================================
// Types
// ============================================================================

export interface LoginRequest {
  username: string
  password: string
}

export interface LoginResponse {
  access_token: string
  token_type: string
  user: {
    id: number
    username: string
    role: 'admin' | 'member' | 'viewer'
    tenant_id: number
    tenant_name: string
    email?: string
    timezone_iana?: string | null
  }
}

export interface ProfileResponse {
  id: number
  username: string
  email: string | null
  role: 'admin' | 'member' | 'viewer'
  tenant_id: number
  tenant_name: string
  status: string
  last_login_at: string | null
  created_at: string
  updated_at: string
  permissions: string[]
  preferences: {
    timezone_iana: string | null
  }
}

export interface ChangePasswordData {
  oldPassword: string
  newPassword: string
  confirmPassword: string
}

export interface UpdateProfilePreferencesRequest {
  timezone_iana: string | null
}

// ============================================================================
// API Functions
// ============================================================================

/**
 * Login with username and password
 */
export async function login(credentials: LoginRequest): Promise<LoginResponse> {
  const res = await api.post<LoginResponse>('/auth/login', credentials)
  return res.data
}

/**
 * Get current user's profile (including permissions)
 */
export async function getCurrentUserProfile(): Promise<ProfileResponse> {
  const res = await api.get<ProfileResponse>('/auth/profile')
  return res.data
}

/**
 * Update current user's profile preferences.
 */
export async function updateCurrentUserPreferences(
  data: UpdateProfilePreferencesRequest
): Promise<ProfileResponse> {
  const res = await api.patch<ProfileResponse>('/auth/profile/preferences', data)
  return res.data
}

/**
 * Change current user's password
 */
export async function changePassword(data: ChangePasswordData): Promise<void> {
  await api.post('/auth/profile/change-password', {
    old_password: data.oldPassword,
    new_password: data.newPassword,
    confirm_password: data.confirmPassword,
  })
}
