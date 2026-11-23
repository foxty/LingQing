import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import i18n from '@/i18n/config'
import { ChevronRight, Info } from 'lucide-react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

i18n.addResourceBundle(
  'en',
  'translation',
  {
    containerDetailHeader: {
      details: 'About this item',
    },
  },
  true,
  true,
)

i18n.addResourceBundle(
  'zh',
  'translation',
  {
    containerDetailHeader: {
      details: '查看详情',
    },
  },
  true,
  true,
)

interface ContainerDetailHeaderProps {
  parentLabel: string
  onParentNavigate: () => void
  title: string
  /** Actions or status controls tied to the current entity (e.g. sync), beside the breadcrumb leaf. */
  titleAddon?: ReactNode
  /** Entity metadata; opens from an info control on the breadcrumb row when set. */
  meta?: ReactNode
}

export default function ContainerDetailHeader({
  parentLabel,
  onParentNavigate,
  title,
  titleAddon,
  meta,
}: ContainerDetailHeaderProps) {
  const { t } = useTranslation()

  return (
    <div className="min-w-0">
      <nav
        aria-label="Breadcrumb"
        className="flex flex-wrap items-baseline gap-x-1.5 gap-y-2 text-sm text-muted-foreground"
      >
        <button
          type="button"
          onClick={onParentNavigate}
          className="shrink-0 text-sm hover:text-foreground transition-colors"
        >
          {parentLabel}
        </button>
        <ChevronRight className="relative top-0.5 h-4 w-4 shrink-0" aria-hidden />
        <h1
          className="min-w-0 max-w-full truncate text-xl font-semibold leading-tight tracking-tight text-foreground"
          aria-current="page"
        >
          {title}
        </h1>
        {titleAddon ? <div className="shrink-0">{titleAddon}</div> : null}
        {meta ? (
          <Popover>
            <PopoverTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="relative top-0.5 h-8 w-8 shrink-0 text-muted-foreground"
                aria-label={t('containerDetailHeader.details')}
              >
                <Info className="h-4 w-4" aria-hidden />
              </Button>
            </PopoverTrigger>
            <PopoverContent align="start" className="w-80 max-w-[calc(100vw-2rem)] text-sm text-muted-foreground">
              {meta}
            </PopoverContent>
          </Popover>
        ) : null}
      </nav>
    </div>
  )
}