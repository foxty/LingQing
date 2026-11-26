import { cn } from '@/lib/utils'
import {
  addScopesUnique,
  filterScopeSuggestions,
  normalizeScopeToken,
  removeScope,
  splitScopeTokens,
} from '@/lib/oauthScopeChips'
import { X } from 'lucide-react'
import { useCallback, useId, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'

i18n.addResourceBundle(
  'en',
  'translation',
  {
    components: {
      oauthScopeChipField: {
        removeScope: 'Remove scope {{scope}}',
        addCustom: 'Add "{{scope}}"',
      },
    },
  },
  true,
  true,
)

i18n.addResourceBundle(
  'zh',
  'translation',
  {
    components: {
      oauthScopeChipField: {
        removeScope: '移除 scope {{scope}}',
        addCustom: '添加「{{scope}}」',
      },
    },
  },
  true,
  true,
)

type OAuthScopeChipFieldProps = {
  id?: string
  scopes: string[]
  /** Preset scopes for autocomplete; omit for custom-only entry. */
  suggestions?: readonly string[]
  onChange: (scopes: string[]) => void
  disabled?: boolean
  errorMsg?: string
  placeholder?: string
  onFocusInput?: () => void
}

const EMPTY_SCOPE_SUGGESTIONS: readonly string[] = []

export default function OAuthScopeChipField({
  id: idProp,
  scopes,
  suggestions = EMPTY_SCOPE_SUGGESTIONS,
  onChange,
  disabled = false,
  errorMsg,
  placeholder,
  onFocusInput,
}: OAuthScopeChipFieldProps) {
  const { t } = useTranslation()
  const generatedId = useId()
  const inputId = idProp ?? generatedId
  const listboxId = `${inputId}-suggestions`
  const inputRef = useRef<HTMLInputElement>(null)
  const [draft, setDraft] = useState('')
  const [focused, setFocused] = useState(false)

  const hasError = Boolean(errorMsg?.trim())

  const matchingSuggestions = useMemo(
    () => filterScopeSuggestions(suggestions, scopes, draft),
    [draft, scopes, suggestions],
  )

  const draftNormalized = normalizeScopeToken(draft)
  const showCustomAdd =
    focused &&
    draftNormalized.length > 0 &&
    !scopes.includes(draftNormalized) &&
    !matchingSuggestions.some((item) => item === draftNormalized)

  const showSuggestions = focused && !disabled && (matchingSuggestions.length > 0 || showCustomAdd)

  const commitDraft = useCallback(() => {
    const token = normalizeScopeToken(draft)
    if (!token) {
      return
    }
    onChange(addScopesUnique(scopes, [token]))
    setDraft('')
  }, [draft, onChange, scopes])

  const addScope = useCallback(
    (scope: string) => {
      onChange(addScopesUnique(scopes, [scope]))
      setDraft('')
      inputRef.current?.focus()
    },
    [onChange, scopes],
  )

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter' || event.key === ',') {
      event.preventDefault()
      commitDraft()
      return
    }
    if (event.key === 'Backspace' && !draft && scopes.length > 0) {
      event.preventDefault()
      onChange(scopes.slice(0, -1))
    }
  }

  const handlePaste = (text: string) => {
    const tokens = splitScopeTokens(text)
    if (tokens.length === 0) {
      return
    }
    onChange(addScopesUnique(scopes, tokens))
    setDraft('')
  }

  return (
    <div className="space-y-1.5">
      <div
        className={cn(
          'relative flex min-h-9 w-full flex-wrap items-center gap-1 rounded-md border border-input bg-background px-2 py-1.5 text-sm',
          'focus-within:ring-2 focus-within:ring-ring focus-within:ring-offset-2',
          disabled && 'cursor-not-allowed opacity-50',
          hasError && 'border-destructive focus-within:ring-destructive',
        )}
        onClick={() => inputRef.current?.focus()}
      >
        {scopes.map((scope) => (
          <span
            key={scope}
            className="inline-flex max-w-full items-center gap-0.5 rounded-md border border-border bg-secondary px-1.5 py-0.5 font-mono text-xs text-foreground"
          >
            <span className="truncate max-w-[240px]">{scope}</span>
            {!disabled ? (
              <button
                type="button"
                className="rounded-sm text-muted-foreground hover:text-foreground"
                aria-label={t('components.oauthScopeChipField.removeScope', { scope })}
                onClick={(event) => {
                  event.stopPropagation()
                  onChange(removeScope(scopes, scope))
                }}
              >
                <X className="h-3 w-3" aria-hidden />
              </button>
            ) : null}
          </span>
        ))}
        <input
          ref={inputRef}
          id={inputId}
          type="text"
          value={draft}
          disabled={disabled}
          placeholder={scopes.length === 0 ? placeholder : undefined}
          className="min-w-[8rem] flex-1 border-0 bg-transparent p-0 font-mono text-xs outline-none placeholder:text-muted-foreground disabled:cursor-not-allowed"
          aria-invalid={hasError || undefined}
          aria-expanded={showSuggestions}
          aria-controls={showSuggestions ? listboxId : undefined}
          aria-autocomplete="list"
          onFocus={() => {
            setFocused(true)
            onFocusInput?.()
          }}
          onBlur={() => {
            if (normalizeScopeToken(draft)) {
              commitDraft()
            }
            window.setTimeout(() => setFocused(false), 120)
          }}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={handleKeyDown}
          onPaste={(event) => {
            const text = event.clipboardData.getData('text')
            if (/[\s,]/.test(text)) {
              event.preventDefault()
              handlePaste(text)
            }
          }}
        />
        {showSuggestions ? (
          <ul
            id={listboxId}
            role="listbox"
            className="absolute left-0 right-0 top-full z-20 mt-1 max-h-40 overflow-auto rounded-md border border-border bg-popover py-1 shadow-md"
          >
            {matchingSuggestions.map((scope) => (
              <li key={scope} role="option">
                <button
                  type="button"
                  className="w-full px-3 py-1.5 text-left font-mono text-xs hover:bg-accent"
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => addScope(scope)}
                >
                  {scope}
                </button>
              </li>
            ))}
            {showCustomAdd ? (
              <li role="option">
                <button
                  type="button"
                  className="w-full px-3 py-1.5 text-left text-xs hover:bg-accent"
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => addScope(draftNormalized)}
                >
                  {t('components.oauthScopeChipField.addCustom', { scope: draftNormalized })}
                </button>
              </li>
            ) : null}
          </ul>
        ) : null}
      </div>
      {hasError ? <p className="text-xs text-destructive">{errorMsg}</p> : null}
    </div>
  )
}