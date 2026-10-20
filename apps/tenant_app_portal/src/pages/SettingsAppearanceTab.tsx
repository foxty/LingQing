import i18n from '@/i18n/config'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import PortalLogoImage from '@/components/PortalLogoImage'
import SettingsPageShell from '@/components/SettingsPageShell'
import SettingsSection from '@/components/SettingsSection'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  useDeletePortalLogo,
  usePortalBranding,
  useUpdatePortalBranding,
  useUploadPortalLogo,
} from '@/hooks/usePortalBranding'
import { useAuth } from '@/hooks/useAuth'
import { PERMISSIONS } from '@/lib/permissionRules'
import { Loader2 } from 'lucide-react'
import { Navigate } from 'react-router-dom'

i18n.addResourceBundle(
  'en',
  'translation',
  {
    settings: {
      appearance: 'Appearance',
      appearanceTab: {
        pageDesc: 'Customize the product title, subtitle, and logo shown in the app header and sign-in screen.',
        fields: 'Branding',
        appTitle: 'Product title',
        appTitleHint: 'Replaces the default LingQing title in the header.',
        appSubtitle: 'Subtitle',
        appSubtitleHint: 'Second line under the title (e.g. Analysis Workbench).',
        pageTitle: 'Browser tab title',
        pageTitleHint: 'Optional override for the browser tab. Leave empty to use the default.',
        logo: 'Logo',
        logoHint: 'PNG, JPEG, WebP, or SVG, max 512 KB. Shown beside the title.',
        uploadLogo: 'Upload logo',
        removeLogo: 'Remove logo',
        save: 'Save',
        saveSuccess: 'Appearance saved',
        saveFailed: 'Failed to save appearance',
        logoSaved: 'Logo updated',
        logoRemoved: 'Logo removed',
        logoFailed: 'Logo upload failed',
      },
    },
  },
  true,
  true
)

i18n.addResourceBundle(
  'zh',
  'translation',
  {
    settings: {
      appearance: '外观',
      appearanceTab: {
        pageDesc: '自定义应用顶栏与登录页显示的产品名称、副标题和 Logo。',
        fields: '品牌',
        appTitle: '产品标题',
        appTitleHint: '替换顶栏默认的 LingQing 标题。',
        appSubtitle: '副标题',
        appSubtitleHint: '标题下方的第二行（例如「分析工作台」）。',
        pageTitle: '浏览器标签标题',
        pageTitleHint: '可选；留空则使用平台默认。',
        logo: 'Logo',
        logoHint: 'PNG、JPEG、WebP 或 SVG，最大 512 KB，显示在标题旁。',
        uploadLogo: '上传 Logo',
        removeLogo: '移除 Logo',
        save: '保存',
        saveSuccess: '外观已保存',
        saveFailed: '保存外观失败',
        logoSaved: 'Logo 已更新',
        logoRemoved: 'Logo 已移除',
        logoFailed: 'Logo 上传失败',
      },
    },
  },
  true,
  true
)

export default function SettingsAppearanceTab() {
  const { t } = useTranslation()
  const { hasAny } = useAuth()
  const { data: branding, isLoading } = usePortalBranding()
  const updateMutation = useUpdatePortalBranding()
  const uploadMutation = useUploadPortalLogo()
  const deleteLogoMutation = useDeletePortalLogo()
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [appTitle, setAppTitle] = useState('')
  const [appSubtitle, setAppSubtitle] = useState('')
  const [pageTitle, setPageTitle] = useState('')

  useEffect(() => {
    if (!branding) {
      return
    }
    setAppTitle(branding.app_title ?? '')
    setAppSubtitle(branding.app_subtitle ?? '')
    setPageTitle(branding.page_title ?? '')
  }, [branding])

  const onSave = () => {
    void updateMutation.mutateAsync({
      app_title: appTitle.trim() || null,
      app_subtitle: appSubtitle.trim() || null,
      page_title: pageTitle.trim() || null,
    })
  }

  const onPickLogo = () => {
    fileInputRef.current?.click()
  }

  const onLogoSelected = (file: File | undefined) => {
    if (!file) {
      return
    }
    void uploadMutation.mutateAsync(file)
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  if (!hasAny([PERMISSIONS.TENANT_SETTINGS_WRITE])) {
    return <Navigate to="/settings/models" replace />
  }

  if (isLoading) {
    return (
      <SettingsPageShell>
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          {t('common.loading')}
        </div>
      </SettingsPageShell>
    )
  }

  const hasLogo = Boolean(branding?.logo_url?.trim())
  const saving = updateMutation.isPending
  const logoBusy = uploadMutation.isPending || deleteLogoMutation.isPending

  return (
    <SettingsPageShell>
      <SettingsSection
        title={t('settings.appearanceTab.fields')}
        description={t('settings.appearanceTab.pageDesc')}
        action={
          <Button type="button" onClick={onSave} disabled={saving}>
            {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
            {t('settings.appearanceTab.save')}
          </Button>
        }
        contentClassName="max-w-2xl space-y-6"
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="portal-app-title">{t('settings.appearanceTab.appTitle')}</Label>
            <p className="text-xs text-muted-foreground">{t('settings.appearanceTab.appTitleHint')}</p>
            <Input
              id="portal-app-title"
              value={appTitle}
              onChange={(event) => setAppTitle(event.target.value)}
              maxLength={80}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="portal-app-subtitle">{t('settings.appearanceTab.appSubtitle')}</Label>
            <p className="text-xs text-muted-foreground">{t('settings.appearanceTab.appSubtitleHint')}</p>
            <Input
              id="portal-app-subtitle"
              value={appSubtitle}
              onChange={(event) => setAppSubtitle(event.target.value)}
              maxLength={120}
            />
          </div>
        </div>

        <div className="space-y-2">
          <Label htmlFor="portal-page-title">{t('settings.appearanceTab.pageTitle')}</Label>
          <p className="text-xs text-muted-foreground">{t('settings.appearanceTab.pageTitleHint')}</p>
          <Input
            id="portal-page-title"
            value={pageTitle}
            onChange={(event) => setPageTitle(event.target.value)}
            maxLength={120}
          />
        </div>

        <div className="space-y-2 border-t pt-4">
          <Label>{t('settings.appearanceTab.logo')}</Label>
          <p className="text-xs text-muted-foreground">{t('settings.appearanceTab.logoHint')}</p>
          <div className="flex flex-wrap items-center gap-3">
            {hasLogo ? (
              <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-md border bg-card p-1.5">
                <PortalLogoImage logoUrl={branding?.logo_url} className="max-h-full max-w-full object-contain" />
              </div>
            ) : null}
            <input
              ref={fileInputRef}
              type="file"
              accept="image/png,image/jpeg,image/webp,image/svg+xml"
              className="hidden"
              onChange={(event) => onLogoSelected(event.target.files?.[0])}
            />
            <Button type="button" variant="outline" size="sm" onClick={onPickLogo} disabled={logoBusy}>
              {logoBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              {t('settings.appearanceTab.uploadLogo')}
            </Button>
            {hasLogo ? (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="text-destructive hover:text-destructive"
                onClick={() => void deleteLogoMutation.mutateAsync()}
                disabled={logoBusy}
              >
                {t('settings.appearanceTab.removeLogo')}
              </Button>
            ) : null}
          </div>
        </div>
      </SettingsSection>
    </SettingsPageShell>
  )
}
