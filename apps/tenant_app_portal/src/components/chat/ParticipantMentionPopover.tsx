import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Bot, Loader2, UserRound } from 'lucide-react'
import { searchTenantUserDirectory } from '@/lib/tenantUserDirectoryApi'
import { extractParticipantMentionQuery } from '@/lib/participantMention'
import type { ComposeMentionPayload } from '@/lib/participantMention'

interface ParticipantMentionPopoverProps {
  inputValue: string
  open: boolean
  rosterAgents: { id: number; label: string }[]
  memberUserIds: number[]
  includeUsers?: boolean
  onSelect: (mention: ComposeMentionPayload) => void
}

export default function ParticipantMentionPopover({
  inputValue,
  open,
  rosterAgents,
  memberUserIds,
  includeUsers = true,
  onSelect,
}: ParticipantMentionPopoverProps) {
  const { t } = useTranslation()
  const [loading, setLoading] = useState(false)
  const [users, setUsers] = useState<{ user_id: number; username: string }[]>([])

  const query = extractParticipantMentionQuery(inputValue) ?? ''
  const normalized = query.trim().toLowerCase()

  const filteredAgents = useMemo(() => {
    if (!normalized) return rosterAgents
    return rosterAgents.filter((a) => a.label.toLowerCase().includes(normalized))
  }, [normalized, rosterAgents])

  useEffect(() => {
    if (!open || !includeUsers) {
      setUsers([])
      return
    }
    const timer = window.setTimeout(() => {
      void (async () => {
        setLoading(true)
        try {
          const rows = await searchTenantUserDirectory({
            q: query,
            limit: 15,
            exclude_user_ids: [],
          })
          const memberSet = new Set(memberUserIds)
          setUsers(
            rows.filter((row) => memberUserIds.length === 0 || memberSet.has(row.user_id))
          )
        } catch {
          setUsers([])
        } finally {
          setLoading(false)
        }
      })()
    }, 200)
    return () => window.clearTimeout(timer)
  }, [open, query, memberUserIds, includeUsers])

  if (!open) {
    return null
  }

  const empty = filteredAgents.length === 0 && users.length === 0 && !loading

  return (
    <div className="absolute bottom-full left-0 z-20 mb-1 w-full max-w-md rounded-md border border-border bg-popover p-1 shadow-md">
      {loading ? (
        <div className="flex items-center gap-2 px-2 py-2 text-xs text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          {t('components.shareDialog.searching')}
        </div>
      ) : null}
      {filteredAgents.map((agent) => (
        <button
          key={`agent-${agent.id}`}
          type="button"
          className="flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left text-sm hover:bg-accent"
          onClick={() => onSelect({ type: 'agent', id: agent.id, label: agent.label })}
        >
          <Bot className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          <span className="truncate">{agent.label}</span>
        </button>
      ))}
      {users.map((user) => (
        <button
          key={`user-${user.user_id}`}
          type="button"
          className="flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left text-sm hover:bg-accent"
          onClick={() =>
            onSelect({ type: 'user', id: user.user_id, label: user.username })
          }
        >
          <UserRound className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          <span className="truncate">{user.username}</span>
        </button>
      ))}
      {empty ? (
        <div className="px-2 py-2 text-xs text-muted-foreground">
          {t('components.shareDialog.noUsersFound')}
        </div>
      ) : null}
    </div>
  )
}
