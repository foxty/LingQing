import { ExpandableMarkdownImage } from '@/components/markdown/ExpandableMarkdownImage'
import { useEffect, useState } from 'react'
import api from '@/lib/api'
import { chartImageApiPath } from '@/lib/chartImagePath'
import { documentImageApiPath } from '@/lib/documentImagePath'
import { markdownImagePlaceholderClassName } from '@/lib/markdownImagePresentation'
import { cn } from '@/lib/utils'

type AuthenticatedMarkdownImageProps = {
  src?: string
  alt?: string
  className?: string
}

/** Fetches auth-backed markdown images (document parse + chart artifacts). */
export function AuthenticatedMarkdownImage({ src, alt, className }: AuthenticatedMarkdownImageProps) {
  const apiPath = src ? documentImageApiPath(src) ?? chartImageApiPath(src) : null
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
        className={cn(markdownImagePlaceholderClassName(), className)}
        role="status"
        aria-label={alt ?? 'Loading image'}
      />
    )
  }

  if (loadState === 'error' || !objectUrl) {
    return null
  }

  return (
    <ExpandableMarkdownImage displaySrc={objectUrl} alt={alt} className={className} />
  )
}
