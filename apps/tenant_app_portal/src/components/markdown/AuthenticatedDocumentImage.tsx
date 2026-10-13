import { ExpandableMarkdownImage } from '@/components/markdown/ExpandableMarkdownImage'
import { useEffect, useState } from 'react'
import api from '@/lib/api'
import { documentImageApiPath } from '@/lib/documentImagePath'
import { markdownImagePlaceholderClassName } from '@/lib/markdownImagePresentation'
import { cn } from '@/lib/utils'

type AuthenticatedDocumentImageProps = {
  src?: string
  alt?: string
  className?: string
}

/** Fetches tenant document parse images (auth required). */
export function AuthenticatedDocumentImage({ src, alt, className }: AuthenticatedDocumentImageProps) {
  const apiPath = src ? documentImageApiPath(src) : null
  const [objectUrl, setObjectUrl] = useState<string | null>(null)
  const [loadState, setLoadState] = useState<'loading' | 'ready' | 'error'>('loading')

  useEffect(() => {
    if (!apiPath) {
      setObjectUrl(null)
      setLoadState('loading')
      return
    }

    setLoadState('loading')
    let revoked = false
    let createdUrl: string | null = null
    api
      .get(apiPath, { responseType: 'blob' })
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
        setObjectUrl(url)
        setLoadState('ready')
      })
      .catch(() => {
        if (!revoked) {
          setObjectUrl(null)
          setLoadState('error')
        }
      })

    return () => {
      revoked = true
      if (createdUrl) {
        URL.revokeObjectURL(createdUrl)
      }
    }
  }, [apiPath])

  if (!apiPath) {
    return null
  }

  if (loadState === 'loading') {
    return (
      <div
        className={cn(markdownImagePlaceholderClassName('document'), className)}
        role="status"
        aria-label={alt ?? 'Loading image'}
      />
    )
  }

  if (loadState === 'error' || !objectUrl) {
    return null
  }

  return (
    <ExpandableMarkdownImage
      displaySrc={objectUrl}
      alt={alt}
      kind="document"
      className={className}
    />
  )
}
