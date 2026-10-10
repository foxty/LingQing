import axios from 'axios'
import config from './config'

export interface ApiErrorEnvelope {
  code: string
  message: string
  details: Record<string, unknown>
  request_id: string
}

const INTERNAL_ERROR_PATTERNS = [
  /traceback \(most recent call last\)/i,
  /file "[^"]+\.py"/i,
  /\/users\/|\/home\/|\/var\/|\/private\/var\//i,
  /line \d+, in /i,
]

export function looksLikeInternalError(text: string): boolean {
  const value = text.trim()
  if (!value) return false
  return INTERNAL_ERROR_PATTERNS.some((pattern) => pattern.test(value))
}

export function sanitizeUserFacingMessage(text: string, fallback: string): string {
  const value = text.trim()
  if (!value || looksLikeInternalError(value)) {
    return fallback
  }
  return value.length > 240 ? `${value.slice(0, 237)}…` : value
}

export function getApiErrorMessage(err: unknown, fallback: string): string {
  const axiosErr = err as {
    apiError?: ApiErrorEnvelope
    response?: { data?: { message?: unknown; detail?: unknown } }
    message?: string
  }

  const candidates = [
    axiosErr.apiError?.message,
    typeof axiosErr.response?.data?.message === 'string' ? axiosErr.response.data.message : undefined,
    typeof axiosErr.response?.data?.detail === 'string' ? axiosErr.response.data.detail : undefined,
    typeof axiosErr.message === 'string' ? axiosErr.message : undefined,
  ]

  for (const candidate of candidates) {
    if (typeof candidate === 'string' && candidate.trim()) {
      return sanitizeUserFacingMessage(candidate, fallback)
    }
  }

  return fallback
}

const DEFAULT_PAYLOAD_TOO_LARGE_MESSAGE =
  'The file is too large for upload. Please use a smaller file or split the document.'

export function normalizeApiErrorPayload(data: unknown, status?: number): ApiErrorEnvelope {
  if (status === 429) {
    const payload = (data && typeof data === 'object' ? data : {}) as Record<string, unknown>
    const rawMessage =
      typeof payload.message === 'string'
        ? payload.message
        : typeof payload.detail === 'string'
          ? payload.detail
          : 'Too many requests. Please try again later.'
    return {
      code: 'RATE_LIMITED',
      message: sanitizeUserFacingMessage(rawMessage, 'Too many requests. Please try again later.'),
      details:
        payload.details && typeof payload.details === 'object'
          ? (payload.details as Record<string, unknown>)
          : {},
      request_id: typeof payload.request_id === 'string' ? payload.request_id : '',
    }
  }

  if (status === 413) {
    const payload = (data && typeof data === 'object' ? data : {}) as Record<string, unknown>
    const rawMessage =
      typeof payload.message === 'string'
        ? payload.message
        : typeof payload.detail === 'string'
          ? payload.detail
          : DEFAULT_PAYLOAD_TOO_LARGE_MESSAGE
    return {
      code: typeof payload.code === 'string' ? payload.code : 'PAYLOAD_TOO_LARGE',
      message: sanitizeUserFacingMessage(rawMessage, DEFAULT_PAYLOAD_TOO_LARGE_MESSAGE),
      details:
        payload.details && typeof payload.details === 'object'
          ? (payload.details as Record<string, unknown>)
          : {},
      request_id: typeof payload.request_id === 'string' ? payload.request_id : '',
    }
  }

  if (typeof data === 'string' && /<html/i.test(data)) {
    return {
      code: status === 413 ? 'PAYLOAD_TOO_LARGE' : 'UNKNOWN_ERROR',
      message:
        status === 413
          ? DEFAULT_PAYLOAD_TOO_LARGE_MESSAGE
          : sanitizeUserFacingMessage(data, 'Request failed'),
      details: {},
      request_id: '',
    }
  }

  const payload = (data && typeof data === 'object' ? data : {}) as Record<string, unknown>
  const rawMessage =
    typeof payload.message === 'string'
      ? payload.message
      : typeof payload.detail === 'string'
        ? payload.detail
        : 'Request failed'
  return {
    code: typeof payload.code === 'string' ? payload.code : 'UNKNOWN_ERROR',
    message: sanitizeUserFacingMessage(rawMessage, 'Request failed'),
    details:
      payload.details && typeof payload.details === 'object'
        ? (payload.details as Record<string, unknown>)
        : {},
    request_id: typeof payload.request_id === 'string' ? payload.request_id : '',
  }
}

// Create axios instance factory with common interceptors
const createApiClient = (baseURL: string) => {
  const client = axios.create({
    baseURL,
    headers: {
      'Content-Type': 'application/json',
    },
  })

  // JWT interceptor
  client.interceptors.request.use((config) => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  })

  // Response interceptor for handling 401 and other errors
  client.interceptors.response.use(
    (response) => response,
    (error) => {
      // Handle 401 Unauthorized
      if (error.response?.status === 401) {
        localStorage.removeItem('token')
        localStorage.removeItem('user')
        window.location.href = '/login'
      }

      const normalized = normalizeApiErrorPayload(error.response?.data, error.response?.status)
      error.apiError = normalized
      if (error.response && error.response.data && typeof error.response.data === 'object') {
        error.response.data = {
          ...error.response.data,
          code: normalized.code,
          message: normalized.message,
          detail: normalized.message,
          details: normalized.details,
          request_id: normalized.request_id,
        }
      }
      error.message = normalized.message

      // Log error for debugging
      console.error('API Error:', {
        url: error.config?.url,
        method: error.config?.method,
        status: error.response?.status,
        data: error.response?.data,
        code: normalized.code,
        request_id: normalized.request_id,
      })

      return Promise.reject(error)
    }
  )

  return client
}

// Unified Backend API (auth, tenants, documents, data sources, chat, threads)
export const api = createApiClient(config.backendUrl)

/**
 * Build a full URL for the backend service
 * Useful for SSE streams and other special HTTP scenarios
 * @param path - API path (e.g., '/chat/stream')
 * @returns Full URL ready for fetch/EventSource
 */
export function getBackendUrl(path: string): string {
  const baseUrl = config.backendUrl
  // Remove leading slash from path if present to avoid double slashes
  const cleanPath = path.startsWith('/') ? path : `/${path}`
  return `${baseUrl}${cleanPath}`
}

// Default export for backward compatibility
export default api
