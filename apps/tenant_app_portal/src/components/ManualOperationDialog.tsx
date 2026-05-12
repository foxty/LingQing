import { useEffect, useState } from 'react'

import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'

i18n.addResourceBundle('en', 'translation', {
  components: {
    manualOperation: {
      createTitle: 'Create Manual Operation',
      editTitle: 'Edit Manual Operation',
      createDesc: 'Define a new API operation manually',
      editDesc: 'Edit an existing manual API operation',
      addOperation: 'Add Operation',
      saveChanges: 'Save Changes',
      requestSchema: 'Request Schema (JSON)',
      responseSchema: 'Response Schema (JSON)',
    },
  },
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  components: {
    manualOperation: {
      createTitle: '创建手动操作',
      editTitle: '编辑手动操作',
      createDesc: '手动定义新的 API 操作',
      editDesc: '编辑现有的手动 API 操作',
      addOperation: '添加操作',
      saveChanges: '保存更改',
      requestSchema: '请求 Schema (JSON)',
      responseSchema: '响应 Schema (JSON)',
    },
  },
}, true, true)
import ManualOperationForm from '@/components/ManualOperationForm'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Pencil, Plus } from 'lucide-react'

const MANUAL_REQUEST_SCHEMA_EXAMPLE = `{
  "type": "object",
  "properties": {
    "path": {
      "type": "object",
      "properties": {
        "id": {
          "type": "string"
        }
      },
      "required": ["id"]
    },
    "query": {
      "type": "object"
    },
    "header": {
      "type": "object"
    },
    "body": {
      "type": ["object", "null"]
    }
  }
}`

const MANUAL_RESPONSE_SCHEMA_EXAMPLE = `{
  "status": "200",
  "schema": {
    "type": "object",
    "properties": {
      "id": {
        "type": "string"
      },
      "name": {
        "type": "string"
      }
    }
  }
}`

export interface ManualOperationValues {
  method: string
  pathTemplate: string
  summary: string
  operationId: string
  requestSchemaText: string
  responseSchemaText: string
}

interface ManualOperationDialogProps {
  mode: 'create' | 'edit'
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Pre-populate fields (edit mode). Ignored for create. */
  initialValues?: Partial<
    Pick<
      ManualOperationValues,
      | 'method'
      | 'pathTemplate'
      | 'summary'
      | 'operationId'
      | 'requestSchemaText'
      | 'responseSchemaText'
    >
  >
  disabled?: boolean
  /** Resolves on success; throws on validation / server error (caller handles notifications). */
  onSubmit: (values: ManualOperationValues) => Promise<void>
}

export default function ManualOperationDialog({
  mode,
  open,
  onOpenChange,
  initialValues,
  disabled = false,
  onSubmit,
}: ManualOperationDialogProps) {
  const { t } = useTranslation()
  const [method, setMethod] = useState('GET')
  const [pathTemplate, setPathTemplate] = useState('')
  const [summary, setSummary] = useState('')
  const [operationId, setOperationId] = useState('')
  const [requestSchemaText, setRequestSchemaText] = useState(MANUAL_REQUEST_SCHEMA_EXAMPLE)
  const [responseSchemaText, setResponseSchemaText] = useState(MANUAL_RESPONSE_SCHEMA_EXAMPLE)
  const [submitting, setSubmitting] = useState(false)

  // Sync fields when the dialog opens with initial values (edit mode)
  useEffect(() => {
    if (!open) return
    if (mode === 'edit' && initialValues) {
      setMethod(initialValues.method ?? 'GET')
      setPathTemplate(initialValues.pathTemplate ?? '')
      setSummary(initialValues.summary ?? '')
      setOperationId(initialValues.operationId ?? '')
      setRequestSchemaText(initialValues.requestSchemaText ?? MANUAL_REQUEST_SCHEMA_EXAMPLE)
      setResponseSchemaText(initialValues.responseSchemaText ?? MANUAL_RESPONSE_SCHEMA_EXAMPLE)
    } else if (mode === 'create') {
      setMethod('GET')
      setPathTemplate('')
      setSummary('')
      setOperationId('')
      setRequestSchemaText(MANUAL_REQUEST_SCHEMA_EXAMPLE)
      setResponseSchemaText(MANUAL_RESPONSE_SCHEMA_EXAMPLE)
    }
  }, [open, mode, initialValues])

  const handleSubmit = async () => {
    setSubmitting(true)
    try {
      await onSubmit({
        method,
        pathTemplate,
        summary,
        operationId,
        requestSchemaText,
        responseSchemaText,
      })
      onOpenChange(false)
    } finally {
      setSubmitting(false)
    }
  }

  const isCreate = mode === 'create'

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-5xl max-h-[85vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle>{isCreate ? t('components.manualOperation.createTitle') : t('components.manualOperation.editTitle')}</DialogTitle>
          <DialogDescription>
            {isCreate ? t('components.manualOperation.createDesc') : t('components.manualOperation.editDesc')}
          </DialogDescription>
        </DialogHeader>

        <div className="flex-1 min-h-0 overflow-y-auto pr-1">
          <ManualOperationForm
            idPrefix={isCreate ? 'create' : 'edit'}
            method={method}
            onMethodChange={setMethod}
            pathTemplate={pathTemplate}
            onPathTemplateChange={setPathTemplate}
            summary={summary}
            onSummaryChange={setSummary}
            operationId={operationId}
            onOperationIdChange={setOperationId}
            showSchemaFields
            requestSchemaText={requestSchemaText}
            onRequestSchemaTextChange={setRequestSchemaText}
            responseSchemaText={responseSchemaText}
            onResponseSchemaTextChange={setResponseSchemaText}
          />
        </div>

        <DialogFooter className="shrink-0 border-t pt-3 bg-background">
          <Button onClick={handleSubmit} disabled={disabled || submitting}>
            {isCreate ? (
              <>
                <Plus className="w-4 h-4 mr-2" />
                {t('components.manualOperation.addOperation')}
              </>
            ) : (
              <>
                <Pencil className="w-4 h-4 mr-2" />
                {t('components.manualOperation.saveChanges')}
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
