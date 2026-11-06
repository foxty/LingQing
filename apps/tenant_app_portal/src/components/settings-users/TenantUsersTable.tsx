import TagBindingsDialog from '@/components/TagBindingsDialog'
import TagChips from '@/components/TagChips'
import PaginationBar from '@/components/PaginationBar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { DeactivateUserButton } from '@/components/settings-users/DeactivateUserButton'
import { TENANT_USERS_PAGE_SIZE } from '@/components/settings-users/tenantUsersListModel'
import { TAG_RESOURCE_TYPES, type TagKeyDTO, type TagValueDTO } from '@/lib/tagsApi'
import type { TenantUser, TenantUserRole } from '@/lib/tenantUsersApi'
import { Info, Tag } from 'lucide-react'
import { useTranslation } from 'react-i18next'

export default function TenantUsersTable({
  users,
  loading,
  totalInTenant,
  totalFiltered,
  page,
  totalPages,
  onPageChange,
  canReadTags,
  canManageTags,
  canManageUsers,
  canManageSso,
  tagKeys,
  userTags,
  activeAdminCount,
  currentUserId,
  deactivateBlockedReason,
  onRoleChange,
  onBreakGlassChange,
  onTagsUpdated,
  onOpenReactivate,
  onOpenResetPassword,
  onOpenDeactivate,
}: {
  users: TenantUser[]
  loading: boolean
  totalInTenant: number
  totalFiltered: number
  page: number
  totalPages: number
  onPageChange: (page: number) => void
  canReadTags: boolean
  canManageTags: boolean
  canManageUsers: boolean
  canManageSso: boolean
  tagKeys: TagKeyDTO[]
  userTags: Record<number, TagValueDTO[]>
  activeAdminCount: number
  currentUserId: number | undefined
  deactivateBlockedReason: (userId: number, role: TenantUserRole, membershipStatus: string) => string | null
  onRoleChange: (userId: number, nextRole: TenantUserRole) => void
  onBreakGlassChange: (userId: number, next: boolean) => void
  onTagsUpdated: (resourceId: number, tags: TagValueDTO[]) => void
  onOpenReactivate: (userId: number) => void
  onOpenResetPassword: (userId: number) => void
  onOpenDeactivate: (userId: number) => void
}) {
  const { t } = useTranslation()

  const listMessage = loading && totalInTenant === 0
    ? { colSpan: 6 as const, text: t('common.loading') }
    : !loading && totalInTenant === 0
      ? { colSpan: 6 as const, text: t('settings.usersTab.noUsers') }
      : !loading && totalFiltered === 0
        ? { colSpan: 6 as const, text: t('settings.usersTab.searchNoMatches') }
        : null

  return (
    <div>
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead className="h-10 w-[40px]">ID</TableHead>
            <TableHead className="h-10">{t('settings.usersTab.usernameCol')}</TableHead>
            <TableHead className="h-10">{t('settings.usersTab.roleCol')}</TableHead>
            <TableHead className="h-10">{t('settings.usersTab.statusCol')}</TableHead>
            <TableHead className="h-10">
              <div className="flex items-center gap-1.5">
                {t('settings.usersTab.breakGlassCol')}
                <TooltipProvider delayDuration={200}>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <span className="text-muted-foreground">
                        <Info className="h-3.5 w-3.5" />
                      </span>
                    </TooltipTrigger>
                    <TooltipContent side="top" className="max-w-xs text-left">
                      {t('settings.usersTab.breakGlassHint')}
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              </div>
            </TableHead>
            <TableHead className="h-10 text-right">{t('common.operation')}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {listMessage ? (
            <TableRow>
              <TableCell colSpan={listMessage.colSpan} className="py-10 text-center text-sm text-muted-foreground">
                {listMessage.text}
              </TableCell>
            </TableRow>
          ) : (
            users.map((user) => {
              const blockedReason = deactivateBlockedReason(user.id, user.role, user.membership_status)
              return (
                <TableRow key={user.id}>
                  <TableCell className="py-3 text-sm text-muted-foreground">{user.id}</TableCell>
                  <TableCell className="py-3">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{user.username}</span>
                      {user.id === currentUserId && (
                        <Badge variant="secondary">{t('settings.usersTab.currentUser')}</Badge>
                      )}
                    </div>
                    {canReadTags && (userTags[user.id]?.length || 0) > 0 && (
                      <TagChips tags={userTags[user.id]} tagKeys={tagKeys} className="mt-2" />
                    )}
                  </TableCell>
                  <TableCell className="py-3">
                    <Select
                      value={user.role}
                      onValueChange={(value) => onRoleChange(user.id, value as TenantUserRole)}
                      disabled={
                        !canManageUsers ||
                        loading ||
                        user.membership_status === 'inactive' ||
                        user.id === currentUserId ||
                        (user.role === 'admin' && activeAdminCount <= 1)
                      }
                    >
                      <SelectTrigger className="h-8 w-[120px]">
                        <SelectValue placeholder={t('settings.usersTab.selectRole')} />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="admin">{t('settings.usersTab.admin')}</SelectItem>
                        <SelectItem value="member">{t('settings.usersTab.member')}</SelectItem>
                        <SelectItem value="viewer">{t('settings.usersTab.viewer')}</SelectItem>
                      </SelectContent>
                    </Select>
                  </TableCell>
                  <TableCell className="py-3">
                    <Badge
                      className={
                        user.membership_status === 'inactive'
                          ? 'border-transparent bg-muted text-muted-foreground'
                          : 'border-transparent bg-success/15 text-success'
                      }
                    >
                      {user.membership_status === 'inactive'
                        ? t('settings.usersTab.inactive')
                        : t('settings.usersTab.active')}
                    </Badge>
                  </TableCell>
                  <TableCell className="py-3">
                    <Switch
                      checked={!!user.is_break_glass}
                      onCheckedChange={(v) => onBreakGlassChange(user.id, v)}
                      disabled={!canManageSso || loading || user.membership_status === 'inactive'}
                      aria-label={t('settings.usersTab.breakGlassCol')}
                    />
                  </TableCell>
                  <TableCell className="py-3 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <TagBindingsDialog
                        resourceType={TAG_RESOURCE_TYPES.USER}
                        resourceId={user.id}
                        title={t('settings.usersTab.manageTags')}
                        canManage={canManageTags}
                        canRead={canReadTags}
                        onTagsUpdated={onTagsUpdated}
                      >
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-8 w-8 p-0"
                          disabled={!canReadTags}
                          aria-label={t('settings.usersTab.manageTags')}
                          title={t('settings.usersTab.manageTags')}
                        >
                          <Tag className="h-4 w-4" />
                        </Button>
                      </TagBindingsDialog>
                      {user.membership_status === 'inactive' ? (
                        <Button size="sm" variant="outline" onClick={() => onOpenReactivate(user.id)}>
                          {t('settings.usersTab.reactivate')}
                        </Button>
                      ) : (
                        <>
                          <Button size="sm" variant="outline" onClick={() => onOpenResetPassword(user.id)}>
                            {t('settings.usersTab.resetPassword')}
                          </Button>
                          <DeactivateUserButton
                            label={t('settings.usersTab.deactivate')}
                            disabled={!canManageUsers || !!blockedReason}
                            reason={blockedReason}
                            onClick={() => onOpenDeactivate(user.id)}
                          />
                        </>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              )
            })
          )}
        </TableBody>
      </Table>

      {!listMessage && totalFiltered > 0 ? (
        <div className="mt-3 border-t border-border pt-3">
          <PaginationBar
            page={page}
            pageSize={TENANT_USERS_PAGE_SIZE}
            total={totalFiltered}
            totalPages={totalPages}
            onPageChange={onPageChange}
            showWhenSinglePage={false}
          />
        </div>
      ) : null}
    </div>
  )
}
