import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Check, ChevronsUpDown } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { cn } from '@/lib/utils'
import { filterIanaTimeZones } from '@/lib/timezones'

interface TimezonePickerProps {
  value: string
  onChange: (timeZone: string) => void
  disabled?: boolean
  id?: string
}

export default function TimezonePicker({ value, onChange, disabled = false, id }: TimezonePickerProps) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')

  const options = useMemo(() => filterIanaTimeZones(query, value), [query, value])

  const selectZone = (tz: string) => {
    onChange(tz)
    setQuery('')
    setOpen(false)
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          id={id}
          type="button"
          role="combobox"
          aria-expanded={open}
          disabled={disabled}
          className={cn(
            'flex h-9 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
            'disabled:cursor-not-allowed disabled:opacity-50'
          )}
        >
          <span className={cn('truncate text-left', !value && 'text-muted-foreground')}>
            {value || t('userProfile.timezoneSelectPlaceholder')}
          </span>
          <ChevronsUpDown className="h-4 w-4 shrink-0 opacity-50" aria-hidden />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-[var(--radix-popover-trigger-width)] p-2" align="start">
        <Input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={t('userProfile.timezoneSearchPlaceholder')}
          className="h-8"
          autoFocus
        />
        <div className="mt-2 max-h-60 space-y-0.5 overflow-y-auto overscroll-contain [scrollbar-gutter:stable]">
          {options.length === 0 ? (
            <p className="px-2 py-3 text-sm text-muted-foreground">{t('userProfile.timezoneNoResults')}</p>
          ) : (
            options.map((tz) => {
              const selected = tz === value
              return (
                <button
                  key={tz}
                  type="button"
                  className={cn(
                    'flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm',
                    'hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                    selected && 'bg-muted'
                  )}
                  onClick={() => selectZone(tz)}
                >
                  {selected ? (
                    <Check className="h-3.5 w-3.5 shrink-0 text-primary" aria-hidden />
                  ) : (
                    <span className="inline-block h-3.5 w-3.5 shrink-0" aria-hidden />
                  )}
                  <span className="min-w-0 truncate font-mono text-xs">{tz}</span>
                </button>
              )
            })
          )}
        </div>
        {!query.trim() ? (
          <p className="mt-2 px-1 text-[11px] text-muted-foreground">{t('userProfile.timezoneSearchHint')}</p>
        ) : null}
      </PopoverContent>
    </Popover>
  )
}