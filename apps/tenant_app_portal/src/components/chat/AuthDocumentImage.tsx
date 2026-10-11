import { useEffect, useState } from 'react'
import api from '@/lib/api'
import { documentImageApiPath } from '@/lib/documentImagePath'

export function AuthDocumentImage({ src, alt }: { src?: string; alt?: string }) {
  const [objectUrl, setObjectUrl] = useState<string | null>(null)

  useEffect(() => {
    if (!src) {
      return
    }
    const apiPath = documentImageApiPath(src)
    if (!apiPath) {
      return
    }

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
      })
      .catch(() => {
        if (!revoked) {
          setObjectUrl(null)
        }
      })

    return () => {
      revoked = true
      if (createdUrl) {
        URL.revokeObjectURL(createdUrl)
      }
    }
  }, [src])

  if (!objectUrl) {
    return null
  }

  return (
    <img src={objectUrl} alt={alt ?? ''} className="my-2 max-h-96 max-w-full rounded-md border" />
  )
}
