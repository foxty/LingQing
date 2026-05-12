import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Search, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'

interface DocumentListToolbarProps {
  searchQuery: string
  onSearchQueryChange: (value: string) => void
  onClearSearchQuery: () => void
}

export default function DocumentListToolbar({
  searchQuery,
  onSearchQueryChange,
  onClearSearchQuery,
}: DocumentListToolbarProps) {
  const { t } = useTranslation()

  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="relative w-full sm:w-64">
        <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
        <Input
          placeholder={t('knowledgeBase.searchPlaceholder')}
          value={searchQuery}
          onChange={(e) => onSearchQueryChange(e.target.value)}
          className="pl-8 h-9"
        />
        {searchQuery && (
          <Button
            variant="ghost"
            size="sm"
            className="absolute right-1 top-1 h-7 w-7 p-0"
            onClick={onClearSearchQuery}
          >
            <X className="h-3 w-3" />
          </Button>
        )}
      </div>
    </div>
  )
}
