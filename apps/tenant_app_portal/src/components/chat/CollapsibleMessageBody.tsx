import { ChevronDown, ChevronUp } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import { cn } from '@/lib/utils'

i18n.addResourceBundle(
  'en',
  'translation',
  {
    components: {
      collapsibleMessageBody: {
        showMore: 'Show more',
        showLess: 'Show less',
      },
    },
  },
  true,
  true
)

i18n.addResourceBundle(
  'zh',
  'translation',
  {
    components: {
      collapsibleMessageBody: {
        showMore: '展开全文',
        showLess: '收起',
      },
    },
  },
  true,
  true
)

/** Matches parent bubble background for fade + toggle contrast. */
export type CollapsibleMessageBodyTone = 'default' | 'onPrimary'

const TONE_CLASSES: Record<
  CollapsibleMessageBodyTone,
  { fadeFromClass: string; toggleButtonClass: string }
> = {
  default: {
    fadeFromClass: 'from-muted',
    toggleButtonClass: 'text-muted-foreground',
  },
  onPrimary: {
    fadeFromClass: 'from-primary',
    toggleButtonClass: 'text-primary-foreground/90',
  },
}

const DEFAULT_COLLAPSE_CHAR_THRESHOLD = 1200
const DEFAULT_MAX_HEIGHT_CLASS = 'max-h-96'

export interface CollapsibleMessageBodyProps {
  children: React.ReactNode
  /** Plain-text length hint; collapsible when at or above threshold. */
  contentLength?: number
  collapseCharThreshold?: number
  maxHeightClass?: string
  tone?: CollapsibleMessageBodyTone
  isStreaming?: boolean
}

export default function CollapsibleMessageBody({
  children,
  contentLength = 0,
  collapseCharThreshold = DEFAULT_COLLAPSE_CHAR_THRESHOLD,
  maxHeightClass = DEFAULT_MAX_HEIGHT_CLASS,
  tone = 'default',
  isStreaming = false,
}: CollapsibleMessageBodyProps) {
  const { t } = useTranslation()
  const toneClasses = TONE_CLASSES[tone]

  const shouldOfferCollapse = useMemo(
    () => !isStreaming && contentLength >= collapseCharThreshold,
    [contentLength, collapseCharThreshold, isStreaming]
  )

  const [expanded, setExpanded] = useState(false)

  if (!shouldOfferCollapse) {
    return <>{children}</>
  }

  return (
    <div className="min-w-0">
      <div className={cn('relative', !expanded && maxHeightClass, !expanded && 'overflow-hidden')}>
        {children}
        {!expanded ? (
          <div
            className={cn(
              'pointer-events-none absolute inset-x-0 bottom-0 h-12 bg-gradient-to-t to-transparent',
              toneClasses.fadeFromClass
            )}
            aria-hidden
          />
        ) : null}
      </div>
      <button
        type="button"
        onClick={() => setExpanded((prev) => !prev)}
        aria-expanded={expanded}
        className={cn(
          'mt-2 flex items-center gap-1 text-xs font-medium underline-offset-2 hover:underline',
          toneClasses.toggleButtonClass
        )}
      >
        {expanded ? (
          <>
            <ChevronUp className="h-3 w-3" aria-hidden />
            {t('components.collapsibleMessageBody.showLess')}
          </>
        ) : (
          <>
            <ChevronDown className="h-3 w-3" aria-hidden />
            {t('components.collapsibleMessageBody.showMore')}
          </>
        )}
      </button>
    </div>
  )
}