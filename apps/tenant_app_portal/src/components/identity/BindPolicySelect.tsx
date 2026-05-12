import i18n from '@/i18n/config'
import { useTranslation } from 'react-i18next'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { FirstLoginPolicy } from '@/lib/ssoApi'

i18n.addResourceBundle(
  'en',
  'translation',
  {
    identity: {
      bindPolicy: {
        label: 'Bind policy',
        jit_create: 'Auto-create user (JIT)',
        pending_approval: 'Require admin approval',
        reject_unknown: 'Reject unknown users',
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
    identity: {
      bindPolicy: {
        label: '绑定策略',
        jit_create: '自动创建用户（JIT）',
        pending_approval: '需要管理员审批',
        reject_unknown: '拒绝未知用户',
      },
    },
  },
  true,
  true
)

type Props = {
  value: FirstLoginPolicy
  onChange: (value: FirstLoginPolicy) => void
  disabled?: boolean
  className?: string
}

const POLICIES: FirstLoginPolicy[] = ['jit_create', 'pending_approval', 'reject_unknown']

export default function BindPolicySelect({ value, onChange, disabled, className }: Props) {
  const { t } = useTranslation()

  return (
    <Select value={value} onValueChange={(v) => onChange(v as FirstLoginPolicy)} disabled={disabled}>
      <SelectTrigger className={className ?? 'w-full sm:w-[240px]'}>
        <SelectValue placeholder={t('identity.bindPolicy.label')} />
      </SelectTrigger>
      <SelectContent>
        {POLICIES.map((policy) => (
          <SelectItem key={policy} value={policy}>
            {t(`identity.bindPolicy.${policy}`)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
