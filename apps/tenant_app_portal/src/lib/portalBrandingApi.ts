import api from './api'
import config from './config'

export interface PortalBranding {
  app_title: string | null
  app_subtitle: string | null
  page_title: string | null
  logo_url: string | null
}

export interface UpdatePortalBrandingPayload {
  app_title?: string | null
  app_subtitle?: string | null
  page_title?: string | null
}

export function resolvePortalLogoSrc(logoUrl: string | null | undefined): string | null {
  if (!logoUrl?.trim()) {
    return null
  }
  if (logoUrl.startsWith('http://') || logoUrl.startsWith('https://')) {
    return logoUrl
  }
  const base = config.backendUrl.replace(/\/$/, '')
  const path = logoUrl.startsWith('/') ? logoUrl : `/${logoUrl}`
  return `${base}${path}`
}

export async function getPortalBranding(): Promise<PortalBranding> {
  const response = await api.get<PortalBranding>('/tenants/portal-branding')
  return response.data
}

export async function updatePortalBranding(payload: UpdatePortalBrandingPayload): Promise<PortalBranding> {
  const response = await api.put<PortalBranding>('/tenants/portal-branding', payload)
  return response.data
}

export async function uploadPortalLogo(file: File): Promise<PortalBranding> {
  const form = new FormData()
  form.append('file', file)
  const response = await api.post<PortalBranding>('/tenants/portal-branding/logo', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return response.data
}

export async function deletePortalLogo(): Promise<PortalBranding> {
  const response = await api.delete<PortalBranding>('/tenants/portal-branding/logo')
  return response.data
}

export async function getPublicPortalBranding(slug: string): Promise<PortalBranding> {
  const response = await api.get<PortalBranding>(`/public/tenants/${encodeURIComponent(slug)}/portal-branding`)
  return response.data
}
