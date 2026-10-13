import { AuthenticatedDocumentImage } from '@/components/markdown/AuthenticatedDocumentImage'
import { ExpandableMarkdownImage } from '@/components/markdown/ExpandableMarkdownImage'
import { directMarkdownImageSrc, markdownImageMode } from '@/lib/markdownImagePath'

type MarkdownImageProps = {
  src?: string
  alt?: string
  className?: string
}

/**
 * Shared `img` renderer for markdown (chat, reports, previews).
 * Document images use authenticated blob fetch; chart SVGs and other static assets use proxied URLs.
 */
export function MarkdownImage({ src, alt, className }: MarkdownImageProps) {
  if (!src) {
    return null
  }

  const mode = markdownImageMode(src)
  if (mode === 'authenticated-document') {
    return <AuthenticatedDocumentImage src={src} alt={alt} className={className} />
  }

  const directSrc = directMarkdownImageSrc(src)
  if (mode === 'direct' && directSrc) {
    return (
      <ExpandableMarkdownImage
        displaySrc={directSrc}
        alt={alt}
        kind="chart"
        className={className}
      />
    )
  }

  return null
}
