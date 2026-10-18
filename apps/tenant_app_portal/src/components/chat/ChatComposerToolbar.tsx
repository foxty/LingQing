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
import { MoreHorizontal } from 'lucide-react'
import { useTranslation } from 'react-i18next'

interface ChatComposerToolbarProps {
  inputDisabled: boolean
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
}

export default function ChatComposerToolbar({
  inputDisabled,
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
}: ChatComposerToolbarProps) {
  const { t } = useTranslation()

  const thinkingEffortLabel = t('workbench.thinkingEffort')

  return (
    <div className="flex items-center justify-between gap-2 border-t border-border/60 px-2 py-1.5">
      <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
        {showRuntimeControls ? (
          <>
            {modelDisplayLabel ? (
              <Badge
                variant="secondary"
                className={`max-w-[min(100%,12rem)] shrink-0 truncate font-normal ${
                  modelDisplayLabel === agentModelId ? 'font-mono' : ''
                }`}
                title={modelChipTitle}
              >
                {modelDisplayLabel}
              </Badge>
            ) : null}
            {thinkingEffortControlEnabled && thinkingEffortOptions.length > 0 ? (
              <div className="flex min-w-0 items-center gap-1.5">
                <span
                  id="workbench-thinking-effort-label"
                  className="shrink-0 text-xs text-muted-foreground"
                >
                  {thinkingEffortLabel}
                </span>
                <Select
                  value={thinkingEffort}
                  onValueChange={(value) => onThinkingEffortChange(value as ThinkingEffort)}
                  disabled={inputDisabled}
                >
                  <SelectTrigger
                    className="h-8 w-auto max-w-[10rem] gap-1 border-dashed px-2 text-xs font-normal"
                    aria-labelledby="workbench-thinking-effort-label"
                  >
                    <SelectValue placeholder={thinkingEffortLabel} />
                  </SelectTrigger>
                  <SelectContent align="start">
                    {thinkingEffortOptions.map((option) => (
                      <SelectItem key={option.value} value={option.value} className="text-xs">
                        {option.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            ) : null}
          </>
        ) : (
          <span className="text-xs text-muted-foreground">{t('workbench.composerAttachHint')}</span>
        )}
      </div>

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-9 w-9 shrink-0"
            disabled={inputDisabled}
            aria-label={t('workbench.composerSettings')}
          >
            <MoreHorizontal className="h-4 w-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-56">
          <p className="px-2 py-1.5 text-[11px] leading-snug text-muted-foreground">{sendKeyHint}</p>
          <DropdownMenuSeparator />
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
            onValueChange={(value) => onArtifactsAutoOpenChange(value as ArtifactsAutoOpenPreference)}
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
    </div>
  )
}
