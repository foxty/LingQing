import { useMemo, useState } from 'react'
import { ChevronsUpDown, X } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { cn } from '@/lib/utils'

export type MultiSelectOption = {
  id: string
  label: string
  description?: string
}

type MultiSelectFieldProps = {
  label: string
  help?: string
  placeholder: string
  searchPlaceholder: string
  emptyOptionsMessage: string
  noResultsMessage: string
  options: MultiSelectOption[]
  selectedIds: string[]
  disabled?: boolean
  onChange: (selectedIds: string[]) => void
}

function SelectionSurface({
  selectedOptions,
  placeholder,
  disabled,
  onRemove,
}: {
  selectedOptions: MultiSelectOption[]
  placeholder: string
  disabled?: boolean
  onRemove?: (id: string) => void
}) {
  return (
    <>
      <div className="flex min-w-0 flex-1 flex-wrap items-center gap-1">
        {selectedOptions.map((option) => (
          <span
            key={option.id}
            className="inline-flex max-w-full items-center gap-0.5 rounded-md border border-success/25 bg-success/15 px-1.5 py-0.5 text-xs font-medium text-success"
          >
            <span className="truncate">{option.label}</span>
            {!disabled && onRemove ? (
              <button
                type="button"
                className="rounded-sm text-success/70 hover:text-success"
                aria-label={`Remove ${option.label}`}
                onClick={(event) => {
                  event.preventDefault()
                  event.stopPropagation()
                  onRemove(option.id)
                }}
              >
                <X className="h-3 w-3" />
              </button>
            ) : null}
          </span>
        ))}
        {selectedOptions.length === 0 ? (
          <span className="text-sm text-muted-foreground">{placeholder}</span>
        ) : null}
      </div>
      {!disabled ? <ChevronsUpDown className="h-4 w-4 shrink-0 opacity-50" aria-hidden /> : null}
    </>
  )
}

const triggerClassName = cn(
  'flex min-h-9 w-full items-center gap-2 rounded-md border border-input bg-background px-2 py-1.5 text-sm',
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
  'disabled:cursor-not-allowed disabled:opacity-50'
)

export default function MultiSelectField({
  label,
  help,
  placeholder,
  searchPlaceholder,
  emptyOptionsMessage,
  noResultsMessage,
  options,
  selectedIds,
  disabled = false,
  onChange,
}: MultiSelectFieldProps) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')

  const optionById = useMemo(() => new Map(options.map((option) => [option.id, option])), [options])

  const selectedOptions = selectedIds
    .map((id) => optionById.get(id))
    .filter((option): option is MultiSelectOption => option !== undefined)

  const availableOptions = useMemo(() => {
    const selected = new Set(selectedIds)
    const normalized = query.trim().toLowerCase()
    return options.filter((option) => {
      if (selected.has(option.id)) {
        return false
      }
      if (!normalized) {
        return true
      }
      const haystack = `${option.label} ${option.description ?? ''}`.toLowerCase()
      return haystack.includes(normalized)
    })
  }, [options, query, selectedIds])

  const addOption = (id: string) => {
    if (selectedIds.includes(id)) {
      return
    }
    onChange([...selectedIds, id])
    setQuery('')
  }

  const removeOption = (id: string) => {
    onChange(selectedIds.filter((item) => item !== id))
  }

  const listContent = (
    <>
      <Input
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder={searchPlaceholder}
        className="h-8"
      />
      <div className="mt-2 max-h-48 space-y-0.5 overflow-y-auto">
        {options.length === 0 ? (
          <p className="px-2 py-3 text-sm text-muted-foreground">{emptyOptionsMessage}</p>
        ) : availableOptions.length === 0 ? (
          <p className="px-2 py-3 text-sm text-muted-foreground">{noResultsMessage}</p>
        ) : (
          availableOptions.map((option) => (
            <button
              key={option.id}
              type="button"
              className={cn(
                'flex w-full flex-col items-start rounded-md px-2 py-1.5 text-left text-sm',
                'hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring'
              )}
              onClick={() => addOption(option.id)}
            >
              <span className="font-medium">{option.label}</span>
              {option.description ? (
                <span className="text-xs text-muted-foreground line-clamp-2">{option.description}</span>
              ) : null}
            </button>
          ))
        )}
      </div>
    </>
  )

  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      {help ? <p className="text-xs text-muted-foreground">{help}</p> : null}
      {disabled ? (
        <div className={cn(triggerClassName, 'cursor-default')}>
          <SelectionSurface selectedOptions={selectedOptions} placeholder={placeholder} disabled />
        </div>
      ) : (
        <Popover open={open} onOpenChange={setOpen}>
          <PopoverTrigger asChild>
            <button type="button" role="combobox" aria-expanded={open} className={triggerClassName}>
              <SelectionSurface
                selectedOptions={selectedOptions}
                placeholder={placeholder}
                onRemove={removeOption}
              />
            </button>
          </PopoverTrigger>
          <PopoverContent className="w-[var(--radix-popover-trigger-width)] p-2" align="start">
            {listContent}
          </PopoverContent>
        </Popover>
      )}
    </div>
  )
}
