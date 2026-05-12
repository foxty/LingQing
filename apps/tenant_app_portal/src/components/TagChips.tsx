import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'

import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { cn } from '@/lib/utils'
import type { TagKeyDTO, TagValueDTO } from '@/lib/tagsApi'

i18n.addResourceBundle('en', 'translation', {
  components: {
    tagChips: {
      valueLabel: '{{key}}: {{value}}',
      moreTags: '+{{count}}',
      allTags: 'All tags',
    },
  },
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  components: {
    tagChips: {
      valueLabel: '{{key}}: {{value}}',
      moreTags: '+{{count}}',
      allTags: '全部标签',
    },
  },
}, true, true)

interface TagChipsProps {
  tags: TagValueDTO[]
  tagKeys: TagKeyDTO[]
  className?: string
  /** Table/list rows: cap visible chips and collapse the rest */
  compact?: boolean
  maxVisible?: number
}

function TagChip({
  value,
  color,
  title,
  maxWidthClass = 'max-w-[140px]',
}: {
  value: string
  color: string
  title?: string
  maxWidthClass?: string
}) {
  return (
    <span
      title={title}
      className={cn(
        'inline-flex items-center truncate rounded-full border px-1.5 py-0 text-[11px] leading-5',
        maxWidthClass
      )}
      style={{ backgroundColor: color, borderColor: color, color: '#fff' }}
    >
      <span className="truncate">{value}</span>
    </span>
  )
}

export default function TagChips({
  tags,
  tagKeys,
  className,
  compact = false,
  maxVisible = 3,
}: TagChipsProps) {
  const { t } = useTranslation()

  const flatTags = useMemo(() => {
    const tagKeyMap = new Map<number, TagKeyDTO>()
    tagKeys.forEach((key) => tagKeyMap.set(key.id, key))

    return tags.map((tag) => {
      const key = tagKeyMap.get(tag.key_id)
      return {
        id: tag.id,
        keyName: key?.name || '',
        value: tag.value,
        color: key?.color || '#64748b',
      }
    })
  }, [tags, tagKeys])

  if (!flatTags.length) {
    return null
  }

  const visibleTags = compact ? flatTags.slice(0, maxVisible) : flatTags
  const hiddenTags = compact ? flatTags.slice(maxVisible) : []

  return (
    <div className={cn('flex flex-wrap items-center gap-1', className)}>
      {visibleTags.map((tag) => (
        <TagChip
          key={tag.id}
          value={tag.value}
          color={tag.color}
          title={t('components.tagChips.valueLabel', { key: tag.keyName, value: tag.value })}
        />
      ))}
      {hiddenTags.length > 0 ? (
        <Popover>
          <PopoverTrigger asChild>
            <button
              type="button"
              className="inline-flex items-center rounded-full border border-border bg-muted px-1.5 py-0 text-[11px] leading-5 text-muted-foreground hover:text-foreground"
            >
              {t('components.tagChips.moreTags', { count: hiddenTags.length })}
            </button>
          </PopoverTrigger>
          <PopoverContent className="w-72 p-3" align="start">
            <div className="mb-2 text-xs font-medium">{t('components.tagChips.allTags')}</div>
            <div className="flex flex-wrap gap-1">
              {flatTags.map((tag) => (
                <TagChip
                  key={tag.id}
                  value={tag.value}
                  color={tag.color}
                  maxWidthClass="max-w-[240px]"
                  title={t('components.tagChips.valueLabel', { key: tag.keyName, value: tag.value })}
                />
              ))}
            </div>
          </PopoverContent>
        </Popover>
      ) : null}
    </div>
  )
}
