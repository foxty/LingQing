import i18n from '@/i18n/config'
import { Outlet } from 'react-router-dom'

i18n.addResourceBundle(
  'en',
  'translation',
  {
    settings: {
      models: 'LLM Models',
      embedding: 'Embedding',
      tags: 'Tags',
      abac: 'ABAC',
      identity: 'Identity',
      sso: 'SSO',
      users: 'Users',
      usage: 'Usage',
      subscription: 'Subscription',
      documentSources: 'Document Sources',
      systemJobs: 'System Jobs',
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
      models: 'LLM 模型',
      embedding: 'Embedding',
      tags: '标签',
      abac: 'ABAC',
      identity: '身份',
      sso: 'SSO',
      slack: 'Slack',
      users: '用户',
      usage: '用量',
      subscription: '订阅',
      documentSources: '文档来源',
      systemJobs: '系统任务',
    },
  },
  true,
  true
)

export default function SettingsPage() {
  return <Outlet />
}
