import { useEffect, useMemo, useState } from 'react'
import api from '@/lib/api'
import { resolvePortalLogoSrc } from '@/lib/portalBrandingApi'
import { cn } from '@/lib/utils'

type PortalLogoImageProps = {
  logoUrl: string | null | undefined
  className?: string
  alt?: string
}

function isPublicLogoUrl(logoUrl: string): boolean {
  return logoUrl.startsWith('/public/') || logoUrl.startsWith('http://') || logoUrl.startsWith('https://')
}

/** Tenant logos on authenticated routes require a bearer token (blob fetch). */
export default function PortalLogoImage({ logoUrl, className, alt = '' }: PortalLogoImageProps) {
  const directSrc = useMemo(() => {
    if (!logoUrl?.trim()) {
      return null
    }
    if (isPublicLogoUrl(logoUrl)) {
      return resolvePortalLogoSrc(logoUrl)
    }
    return null
  }, [logoUrl])

  const [blobSrc, setBlobSrc] = useState<string | null>(null)

  useEffect(() => {
    if (directSrc || !logoUrl?.trim()) {
      setBlobSrc(null)
      return
    }

    const path = logoUrl.startsWith('/') ? logoUrl : `/${logoUrl}`
    let revoked = false
    let createdUrl: string | null = null

    api
      .get(path, { responseType: 'blob' })
      .then((response) => {
        if (revoked) {
          return
        }
        const url = URL.createObjectURL(response.data)
        if (revoked) {
          URL.revokeObjectURL(url)
          return
        }
        createdUrl = url
        setBlobSrc(url)
      })
      .catch(() => {
        if (!revoked) {
          setBlobSrc(null)
        }
      })

    return () => {
      revoked = true
      if (createdUrl) {
        URL.revokeObjectURL(createdUrl)
      }
    }
  }, [directSrc, logoUrl])

  const src = directSrc ?? blobSrc
  if (!src) {
    return null
  }

  return <img src={src} alt={alt} className={cn(className)} />
}
