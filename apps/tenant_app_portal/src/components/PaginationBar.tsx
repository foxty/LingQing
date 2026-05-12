import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import { Button } from '@/components/ui/button'

i18n.addResourceBundle('en', 'translation', {
  components: {
    pagination: {
      showing: 'Showing {{start}} to {{end}} of {{total}}',
      previous: 'Previous',
      next: 'Next',
    },
  },
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  components: {
    pagination: {
      showing: '第 {{start}} - {{end}} 条，共 {{total}} 条',
      previous: '上一页',
      next: '下一页',
    },
  },
}, true, true)

interface PaginationBarProps {
  page: number
  pageSize: number
  total: number
  totalPages: number
  onPageChange: (page: number) => void
  showWhenSinglePage?: boolean
}

export default function PaginationBar({
  page,
  pageSize,
  total,
  totalPages,
  onPageChange,
  showWhenSinglePage = true,
}: PaginationBarProps) {
  const { t } = useTranslation()
  const displayTotalPages = Math.max(1, totalPages)
  const displayPage = Math.min(Math.max(1, page), displayTotalPages)
  const start = total === 0 ? 0 : (displayPage - 1) * pageSize + 1
  const end = total === 0 ? 0 : Math.min(displayPage * pageSize, total)

  if (!showWhenSinglePage && totalPages <= 1) {
    return null
  }

  return (
    <div className="flex items-center justify-between">
      <p className="text-xs text-muted-foreground">
        {t('components.pagination.showing', { start, end, total })}
      </p>
      <div className="flex items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          onClick={() => onPageChange(Math.max(1, displayPage - 1))}
          disabled={displayPage === 1}
          className="h-8"
        >
          {t('components.pagination.previous')}
        </Button>
        <div className="flex items-center gap-1">
          {Array.from({ length: displayTotalPages }, (_, i) => i + 1)
            .filter((p) => p === 1 || p === displayTotalPages || Math.abs(p - displayPage) <= 1)
            .map((p, index, array) => (
              <div key={p} className="flex items-center">
                {index > 0 && array[index - 1] !== p - 1 && (
                  <span className="px-2 text-muted-foreground">...</span>
                )}
                <Button
                  variant={displayPage === p ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => onPageChange(p)}
                  className="h-8 w-8 p-0"
                >
                  {p}
                </Button>
              </div>
            ))}
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => onPageChange(Math.min(displayTotalPages, displayPage + 1))}
          disabled={displayPage >= displayTotalPages}
          className="h-8"
        >
          {t('components.pagination.next')}
        </Button>
      </div>
    </div>
  )
}
