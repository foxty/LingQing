import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import {
  markdownImageExpandedClassName,
  markdownImageInlineClassName,
} from '@/lib/markdownImagePresentation'
import { cn } from '@/lib/utils'

type ExpandableMarkdownImageProps = {
  displaySrc: string
  alt?: string
  className?: string
}

/** Inline markdown image with click-to-expand (same behavior in chat, reports, previews). */
export function ExpandableMarkdownImage({
  displaySrc,
  alt,
  className,
}: ExpandableMarkdownImageProps) {
  const label = alt?.trim() || 'Image'

  return (
    <Dialog>
      <DialogTrigger asChild>
        <button
          type="button"
          className={cn(
            'block max-w-full rounded-md text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
            className,
          )}
          aria-label={label}
        >
          <img
            src={displaySrc}
            alt={alt ?? ''}
            className={markdownImageInlineClassName()}
            loading="lazy"
            decoding="async"
          />
        </button>
      </DialogTrigger>
      <DialogContent
        className="flex w-[min(96vw,72rem)] max-w-[96vw] flex-col gap-0 border bg-background p-3 shadow-lg sm:p-4"
      >
        <DialogTitle className="sr-only">{label}</DialogTitle>
        <div className="flex w-full min-w-0 items-center justify-center overflow-auto">
          <img
            src={displaySrc}
            alt={alt ?? ''}
            className={markdownImageExpandedClassName()}
          />
        </div>
      </DialogContent>
    </Dialog>
  )
}
