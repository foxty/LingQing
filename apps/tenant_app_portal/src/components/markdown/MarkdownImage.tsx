import { AuthenticatedMarkdownImage } from '@/components/markdown/AuthenticatedMarkdownImage'
import { markdownImageMode } from '@/lib/markdownImagePath'

type MarkdownImageProps = {
  src?: string
  alt?: string
  className?: string
}

/** Shared `img` renderer for markdown (chat, reports, previews). */
export function MarkdownImage({ src, alt, className }: MarkdownImageProps) {
  if (!src) {
    return null
  }

  if (markdownImageMode(src) === 'authenticated-document') {
    return <AuthenticatedMarkdownImage src={src} alt={alt} className={className} />
  }

  return null
}
