/**
 * Application configuration
 * Centralized configuration management following KISS principle
 */

// Tenant app service URL - defaults to /api for docker-compose routing through nginx
const backendUrl = import.meta.env.VITE_BACKEND_URL || '/api'
console.log('Tenant app service URL:', backendUrl)

export const config = {
  // Tenant app service URL (unified) - supports relative and absolute paths
  backendUrl: backendUrl,

  // Query cache configuration
  cache: {
    agentsStaleTime: 5 * 60 * 1000, // 5 minutes
    documentsStaleTime: 2 * 60 * 1000, // 2 minutes,
  },

  // Pagination
  pagination: {
    documentsPerPage: 10,
  },

  // Notification durations
  notification: {
    successDuration: 3000, // 3 seconds
    errorDuration: 5000, // 5 seconds
    infoDuration: 3000, // 3 seconds
  },
} as const

export default config
