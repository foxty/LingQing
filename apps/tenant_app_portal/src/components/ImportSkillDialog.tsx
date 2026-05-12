import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'

i18n.addResourceBundle('en', 'translation', {
  components: {
    importSkillDialog: {
      title: 'Import Skill from URL',
      description: 'Paste a skills.sh or GitHub skill link to install it.',
      urlLabel: 'Skill URL',
      urlPlaceholder: 'https://skills.sh/owner/repo/skill-name',
      hint: 'Also supports GitHub tree URLs and owner/repo shorthand.',
      import: 'Import',
      cancel: 'Cancel',
    },
  },
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  components: {
    importSkillDialog: {
      title: '从 URL 导入技能',
      description: '粘贴 skills.sh 或 GitHub 技能链接进行安装。',
      urlLabel: '技能 URL',
      urlPlaceholder: 'https://skills.sh/owner/repo/skill-name',
      hint: '也支持 GitHub tree 链接和 owner/repo 简写。',
      import: '导入',
      cancel: '取消',
    },
  },
}, true, true)

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Download } from 'lucide-react'

interface ImportSkillDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  disabled?: boolean
  onImport: (url: string) => Promise<void>
}

export default function ImportSkillDialog({
  open,
  onOpenChange,
  disabled = false,
  onImport,
}: ImportSkillDialogProps) {
  const { t } = useTranslation()
  const [url, setUrl] = useState('')
  const [importing, setImporting] = useState(false)

  const handleImport = async () => {
    if (!url.trim()) return
    setImporting(true)
    try {
      await onImport(url.trim())
      setUrl('')
      onOpenChange(false)
    } finally {
      setImporting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t('components.importSkillDialog.title')}</DialogTitle>
          <DialogDescription>{t('components.importSkillDialog.description')}</DialogDescription>
        </DialogHeader>

        <div className="space-y-2">
          <Label htmlFor="skill-url">{t('components.importSkillDialog.urlLabel')}</Label>
          <Input
            id="skill-url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder={t('components.importSkillDialog.urlPlaceholder')}
            className="font-mono text-sm"
          />
          <p className="text-xs text-muted-foreground">{t('components.importSkillDialog.hint')}</p>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={importing}>
            {t('components.importSkillDialog.cancel')}
          </Button>
          <Button onClick={handleImport} disabled={disabled || importing || !url.trim()}>
            <Download className="w-4 h-4 mr-2" />
            {t('components.importSkillDialog.import')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
