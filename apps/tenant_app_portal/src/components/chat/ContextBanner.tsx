/**
 * Context Banner Component
 * Displays the selected artifact context above the chat input
 */

import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import { Button } from '@/components/ui/button'

i18n.addResourceBundle('en', 'translation', {
  components: {
    contextBanner: {
      discussing: 'Discussing: {{title}}',
      removeContext: 'Remove context',
    },
  },
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  components: {
    contextBanner: {
      discussing: '正在讨论: {{title}}',
      removeContext: '移除上下文',
    },
  },
}, true, true)
import { formatDate } from '@/lib/dateTime'
import { Artifact } from '@/types'
import { Code, FileText, Layout, TimerIcon, X } from 'lucide-react'

interface ContextBannerProps {
  artifact: Artifact
  onRemove: () => void
}

// Map artifact types to icons
const getArtifactIcon = (type: string) => {
  const iconMap: Record<string, React.ReactNode> = {
    dashboard: <Layout className="w-4 h-4 text-white" />,
    report: <FileText className="w-4 h-4 text-white" />,
    scheduled_task: <TimerIcon className="w-4 h-4 text-white" />,
    code: <Code className="w-4 h-4 text-white" />,
  }
  return iconMap[type] || <FileText className="w-4 h-4 text-white" />
}

// Get color scheme based on artifact type
const getColorScheme = (type: string) => {
  const colorMap: Record<string, { bg: string; border: string; icon: string; text: string }> = {
    dashboard: {
      bg: 'bg-gradient-to-r from-blue-50 to-blue-100',
      border: 'border-blue-200',
      icon: 'bg-blue-500',
      text: 'text-blue-900',
    },
    chart: {
      bg: 'bg-gradient-to-r from-green-50 to-green-100',
      border: 'border-green-200',
      icon: 'bg-green-500',
      text: 'text-green-900',
    },
    report: {
      bg: 'bg-gradient-to-r from-purple-50 to-purple-100',
      border: 'border-purple-200',
      icon: 'bg-purple-500',
      text: 'text-purple-900',
    },
    scheduled_task: {
      bg: 'bg-gradient-to-r from-orange-50 to-orange-100',
      border: 'border-orange-200',
      icon: 'bg-orange-500',
      text: 'text-orange-900',
    },
    code: {
      bg: 'bg-gradient-to-r from-gray-50 to-gray-100',
      border: 'border-gray-200',
      icon: 'bg-gray-500',
      text: 'text-gray-900',
    },
  }
  return (
    colorMap[type] || {
      bg: 'bg-gradient-to-r from-slate-50 to-slate-100',
      border: 'border-slate-200',
      icon: 'bg-slate-500',
      text: 'text-slate-900',
    }
  )
}

export default function ContextBanner({ artifact, onRemove }: ContextBannerProps) {
  const { t } = useTranslation()
  const colors = getColorScheme(artifact.artifact_type)
  const createdDate = artifact.created_at
    ? formatDate(artifact.created_at, { precision: 'date' })
    : null

  return (
    <div
      className={`flex items-center gap-1 px-2 py-1 ${colors.bg} border-b ${colors.border} animate-in slide-in-from-top duration-200`}
      role="status"
      aria-label={t('components.contextBanner.discussing', { title: artifact.title })}
    >
      {/* Icon */}
      <div
        className={`flex-shrink-0 w-6 h-6 rounded ${colors.icon} flex items-center justify-center shadow-sm`}
      >
        {getArtifactIcon(artifact.artifact_type)}
      </div>

      {/* Info */}
      <div className="flex-1 min-w-0">
        <p className={`text-sm font-medium ${colors.text} truncate`}>
          {createdDate}:{artifact.title}
        </p>
      </div>

      {/* Actions */}
      <Button
        size="sm"
        variant="ghost"
        className={`${colors.text} hover:bg-white/50 h-8`}
        onClick={onRemove}
        title={t('components.contextBanner.removeContext')}
        aria-label={t('components.contextBanner.removeContext')}
      >
        <X className="w-4 h-4" />
      </Button>
    </div>
  )
}
