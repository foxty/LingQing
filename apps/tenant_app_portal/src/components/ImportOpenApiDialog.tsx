import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'

i18n.addResourceBundle('en', 'translation', {
  components: {
    importOpenApiDialog: {
      title: 'Import OpenAPI Spec',
      description: 'Paste your OpenAPI specification (JSON/YAML) below',
      import: 'Import',
    },
  },
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  components: {
    importOpenApiDialog: {
      title: '导入 OpenAPI 规范',
      description: '在下方粘贴你的 OpenAPI 规范 (JSON/YAML)',
      import: '导入',
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
import { Textarea } from '@/components/ui/textarea'
import { Upload } from 'lucide-react'

interface ImportOpenApiDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  disabled?: boolean
  /** Called with the pasted content; throws on error (caller handles notifications). */
  onImport: (content: string) => Promise<void>
}

export default function ImportOpenApiDialog({
  open,
  onOpenChange,
  disabled = false,
  onImport,
}: ImportOpenApiDialogProps) {
  const { t } = useTranslation()
  const [content, setContent] = useState('')
  const [importing, setImporting] = useState(false)

  const handleImport = async () => {
    if (!content.trim()) return
    setImporting(true)
    try {
      await onImport(content)
      setContent('')
      onOpenChange(false)
    } finally {
      setImporting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl max-h-[85vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle>{t('components.importOpenApiDialog.title')}</DialogTitle>
          <DialogDescription>{t('components.importOpenApiDialog.description')}</DialogDescription>
        </DialogHeader>

        <div className="flex-1 min-h-0 overflow-y-auto">
          <Textarea
            rows={20}
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder={'{\n  "openapi": "3.0.0",\n  ...\n}'}
            className="font-mono text-xs resize-none h-full"
          />
        </div>

        <DialogFooter className="shrink-0 border-t pt-3 bg-background">
          <Button onClick={handleImport} disabled={disabled || importing || !content.trim()}>
            <Upload className="w-4 h-4 mr-2" />
            {t('components.importOpenApiDialog.import')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
