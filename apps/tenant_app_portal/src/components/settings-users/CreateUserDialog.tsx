import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { TenantUserRole } from '@/lib/tenantUsersApi'
import { useTranslation } from 'react-i18next'

export interface CreateUserFieldErrors {
  username?: string
  email?: string
  password?: string
}

export default function CreateUserDialog({
  open,
  onOpenChange,
  loading,
  username,
  email,
  role,
  password,
  fieldErrors,
  formError,
  onUsernameChange,
  onEmailChange,
  onRoleChange,
  onPasswordChange,
  onSubmit,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  loading: boolean
  username: string
  email: string
  role: TenantUserRole
  password: string
  fieldErrors: CreateUserFieldErrors
  formError: string | null
  onUsernameChange: (value: string) => void
  onEmailChange: (value: string) => void
  onRoleChange: (role: TenantUserRole) => void
  onPasswordChange: (value: string) => void
  onSubmit: () => void
}) {
  const { t } = useTranslation()

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{t('settings.usersTab.newUser.title')}</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">{t('settings.usersTab.newUser.description')}</p>
        {formError ? (
          <Alert variant="destructive">
            <AlertDescription>{formError}</AlertDescription>
          </Alert>
        ) : null}
        <div className="flex flex-col gap-4">
          <div className="space-y-2">
            <Label htmlFor="create-username">{t('settings.usersTab.newUser.username')}</Label>
            <Input
              id="create-username"
              value={username}
              onChange={(event) => onUsernameChange(event.target.value)}
              placeholder={t('settings.usersTab.newUser.usernamePlaceholder')}
              errorMsg={fieldErrors.username}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="create-email">{t('settings.usersTab.newUser.email')}</Label>
            <Input
              id="create-email"
              type="email"
              value={email}
              onChange={(event) => onEmailChange(event.target.value)}
              placeholder="user@example.com"
              errorMsg={fieldErrors.email}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="create-role">{t('settings.usersTab.newUser.role')}</Label>
            <Select value={role} onValueChange={(value) => onRoleChange(value as TenantUserRole)}>
              <SelectTrigger id="create-role" className="w-full">
                <SelectValue placeholder={t('settings.usersTab.selectRole')} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="admin">{t('settings.usersTab.admin')}</SelectItem>
                <SelectItem value="member">{t('settings.usersTab.member')}</SelectItem>
                <SelectItem value="viewer">{t('settings.usersTab.viewer')}</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="create-password">{t('settings.usersTab.newUser.password')}</Label>
            <p className="text-xs text-muted-foreground">{t('settings.usersTab.newUser.passwordRequirements')}</p>
            <Input
              id="create-password"
              type="password"
              value={password}
              onChange={(event) => onPasswordChange(event.target.value)}
              placeholder={t('settings.usersTab.newUser.passwordPlaceholder')}
              autoComplete="new-password"
              errorMsg={fieldErrors.password}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('common.cancel')}
          </Button>
          <Button onClick={() => onSubmit()} disabled={loading}>
            {t('settings.usersTab.newUser.createButton')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
