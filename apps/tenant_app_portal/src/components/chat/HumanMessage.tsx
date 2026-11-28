import { Paperclip, User } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import './aiTurnMessageI18n'
import { Message } from '@/types'
import { getMessageAttachedArtifacts } from '@/lib/messageAttachedArtifacts'
import { usePreferredDateTimeFormat, usePreferredTimezone } from '@/hooks/useCurrentUserProfile'
import { formatChatTimestamp } from '@/lib/dateTime'
import ContextChip from './ContextChip'
import CopyIconButton, { useCopyToClipboard } from '@/components/CopyIconButton'

interface HumanMessageProps {
  message: Message
}

export default function HumanMessage({ message }: HumanMessageProps) {
  const { t, i18n } = useTranslation()
  const timeZone = usePreferredTimezone()
  const dateTimeFormat = usePreferredDateTimeFormat()
  const contextResources = getMessageAttachedArtifacts(message.message_metadata)
  const resetKey = message.message_id
  const { status: copyStatus, copy } = useCopyToClipboard(message.content ?? '', resetKey)

  const formattedTimestamp = message.timestamp
    ? formatChatTimestamp(message.timestamp, {
        timeZone,
        locale: i18n.language,
        formatId: dateTimeFormat,
      })
    : ''

  return (
    <div className="flex items-start space-x-3 flex-row-reverse space-x-reverse">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground">
        <User className="h-4 w-4" />
      </div>
      <div className="flex min-w-0 flex-1 flex-col items-end space-y-1">
        <div className="ml-auto w-fit min-w-[9rem] max-w-[min(92%,42rem)] rounded-lg bg-primary px-4 py-2 text-primary-foreground">
          {contextResources && contextResources.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mb-2">
              {contextResources.map((resource) => (
                <ContextChip
                  key={`artifact-${resource.artifact_id ?? resource.resource_id}`}
                  resource={resource}
                  readOnly
                  variant="message"
                />
              ))}
            </div>
          )}
          {message.artifact && (
            <div className="flex items-center gap-1 text-xs mb-2 px-2 py-1 bg-primary-foreground/20 rounded-md w-fit">
              <Paperclip className="h-3 w-3" />
              <span className="font-medium">{message.artifact.title}</span>
            </div>
          )}
          <p className="text-sm whitespace-pre-wrap">{message.content}</p>
          {copyStatus === 'error' ? (
            <p className="mt-1 text-right text-[11px] text-primary-foreground/90">{t('workbench.copyFailed')}</p>
          ) : null}
          <div className="mt-2 flex min-w-0 flex-wrap items-center justify-end gap-2 text-xs text-primary-foreground/70">
            {formattedTimestamp ? (
              <span className="shrink-0 tabular-nums">{formattedTimestamp}</span>
            ) : null}
            <CopyIconButton
              status={copyStatus}
              onCopy={() => void copy()}
              label={t('workbench.copyHumanMessage')}
              copiedLabel={t('workbench.copied')}
              variant="onPrimary"
            />
          </div>
        </div>
      </div>
    </div>
  )
}