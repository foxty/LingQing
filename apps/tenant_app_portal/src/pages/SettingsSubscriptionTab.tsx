import i18n from '@/i18n/config'
import { useTranslation } from 'react-i18next'
import SettingsSection from '@/components/SettingsSection'

i18n.addResourceBundle('en', 'translation', {
  settings: {
    subscriptionTab: {
      title: 'Subscription',
      description: 'Manage your subscription plan',
      comingSoon: 'Coming Soon',
      comingSoonDesc: 'Subscription management is not yet available',
    }
  }
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  settings: {
    subscriptionTab: {
      title: '订阅',
      description: '管理订阅计划',
      comingSoon: '即将推出',
      comingSoonDesc: '订阅管理功能尚未开放',
    }
  }
}, true, true)

export default function SettingsSubscriptionTab() {
  const { t } = useTranslation()
  return (
    <SettingsSection
      title={t('settings.subscriptionTab.title')}
      description={t('settings.subscriptionTab.description')}
    >
      <div className="flex flex-col items-center justify-center py-12 text-center">
        <p className="mb-2 text-lg font-semibold text-muted-foreground">
          {t('settings.subscriptionTab.comingSoon')}
        </p>
        <p className="text-sm text-muted-foreground">{t('settings.subscriptionTab.comingSoonDesc')}</p>
      </div>
    </SettingsSection>
  )
}
