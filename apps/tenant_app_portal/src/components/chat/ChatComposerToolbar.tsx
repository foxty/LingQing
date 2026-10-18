import './workbenchChatI18n'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { ThinkingEffortOption } from '@/lib/chatApi'
import type { ArtifactsAutoOpenPreference, ThinkingEffort } from '@/lib/userPreferencesTypes'
import { MoreHorizontal, Send } from 'lucide-react'
import { useTranslation } from 'react-i18next'

interface ChatComposerToolbarProps {
  inputDisabled: boolean
  canSend: boolean
  sendKeyHint: string
  showRuntimeControls: boolean
  modelDisplayLabel: string
  modelChipTitle: string
  agentModelId: string
  thinkingEffortControlEnabled: boolean
  thinkingEffortOptions: ThinkingEffortOption[]
  thinkingEffort: ThinkingEffort
  onThinkingEffortChange: (value: ThinkingEffort) => void
  sendKeyPreference: 'enter' | 'ctrl-enter'
  onSendKeyPreferenceChange: (value: 'enter' | 'ctrl-enter') => void
  artifactsAutoOpen: ArtifactsAutoOpenPreference
  onArtifactsAutoOpenChange: (value: ArtifactsAutoOpenPreference) => void
  onSend: () => void
}

export default function ChatComposerToolbar({
  inputDisabled,
  canSend,
  sendKeyHint,
  showRuntimeControls,
  modelDisplayLabel,
  modelChipTitle,
  agentModelId,
  thinkingEffortControlEnabled,
  thinkingEffortOptions,
  thinkingEffort,
  onThinkingEffortChange,
  sendKeyPreference,
  onSendKeyPreferenceChange,
  artifactsAutoOpen,
  onArtifactsAutoOpenChange,
  onSend,
}: ChatComposerToolbarProps) {
  const { t } = useTranslation()

  return (
    <div className="flex flex-wrap items-center justify-between gap-2 bg-muted/25 px-2 py-1.5">
      <div className="flex min-w-0 flex-wrap items-center gap-1.5">
        {showRuntimeControls ? (
          <>
            {modelDisplayLabel ? (
              <Badge
                variant="secondary"
                className={`max-w-[min(100%,14rem)] shrink-0 truncate font-normal ${
                  modelDisplayLabel === agentModelId ? 'font-mono' : ''
                }`}
                title={modelChipTitle}
              >
                {modelDisplayLabel}
              </Badge>
            ) : null}
            {thinkingEffortControlEnabled && thinkingEffortOptions.length > 0 ? (
              <Select
                value={thinkingEffort}
                onValueChange={(value) => onThinkingEffortChange(value as ThinkingEffort)}
                disabled={inputDisabled}
              >
                <SelectTrigger
                  className="h-8 w-auto max-w-[11rem] gap-1 border-dashed px-2 text-xs font-normal"
                  aria-label={t('workbench.thinkingEffort')}
                >
                  <SelectValue placeholder={t('workbench.thinkingEffort')} />
                </SelectTrigger>
                <SelectContent align="start">
                  {thinkingEffortOptions.map((option) => (
                    <SelectItem key={option.value} value={option.value} className="text-xs">
                      {option.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : null}
          </>
        ) : (
          <span className="text-xs text-muted-foreground">{t('workbench.composerAttachHint')}</span>
        )}
      </div>

      <div className="ml-auto flex shrink-0 items-center gap-1">
        <span className="hidden text-[11px] text-muted-foreground sm:inline">{sendKeyHint}</span>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="h-9 w-9"
              disabled={inputDisabled}
              aria-label={t('workbench.composerSettings')}
            >
              <MoreHorizontal className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuLabel>{t('workbench.composerSettings')}</DropdownMenuLabel>
            <DropdownMenuRadioGroup
              value={sendKeyPreference}
              onValueChange={(value) => onSendKeyPreferenceChange(value as 'enter' | 'ctrl-enter')}
            >
              <DropdownMenuRadioItem value="enter">{t('workbench.enterToSend')}</DropdownMenuRadioItem>
              <DropdownMenuRadioItem value="ctrl-enter">
                {t('workbench.ctrlEnterToSend')}
              </DropdownMenuRadioItem>
            </DropdownMenuRadioGroup>
            <DropdownMenuSeparator />
            <DropdownMenuLabel>{t('workbench.artifactsAutoOpen')}</DropdownMenuLabel>
            <DropdownMenuRadioGroup
              value={artifactsAutoOpen}
              onValueChange={(value) =>
                onArtifactsAutoOpenChange(value as ArtifactsAutoOpenPreference)
              }
            >
              <DropdownMenuRadioItem value="never">
                {t('workbench.artifactsAutoOpenNever')}
              </DropdownMenuRadioItem>
              <DropdownMenuRadioItem value="on-new">
                {t('workbench.artifactsAutoOpenOnNew')}
              </DropdownMenuRadioItem>
              <DropdownMenuRadioItem value="always">
                {t('workbench.artifactsAutoOpenAlways')}
              </DropdownMenuRadioItem>
            </DropdownMenuRadioGroup>
          </DropdownMenuContent>
        </DropdownMenu>
        <Button type="button" className="min-h-11 px-4" onClick={onSend} disabled={inputDisabled || !canSend}>
          <Send className="mr-2 h-4 w-4" />
          {t('workbench.send')}
        </Button>
      </div>
    </div>
  )
}
