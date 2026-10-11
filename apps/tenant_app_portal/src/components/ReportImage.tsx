import { AuthDocumentImage } from '@/components/chat/AuthDocumentImage'
import { isDocumentImageSrc } from '@/lib/documentImagePath'
import { cn } from '@/lib/utils'

type ReportImageProps = {
  src?: string
  alt?: string
  className?: string
}

/** Report images: authenticated fetch for document parse assets; plain img otherwise. */
export function ReportImage({ src, alt, className }: ReportImageProps) {
  if (!src) {
    return null
  }
  if (isDocumentImageSrc(src)) {
    return <AuthDocumentImage src={src} alt={alt} />
  }
  return (
    <img
      src={src}
      alt={alt ?? ''}
      className={cn('my-2 max-h-96 max-w-full rounded-md border', className)}
    />
  )
}
