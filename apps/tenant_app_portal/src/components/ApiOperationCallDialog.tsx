import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import { Badge } from '@/components/ui/badge'

i18n.addResourceBundle('en', 'translation', {
  components: {
    apiOperationCall: {
      title: 'Call API Operation',
      operationDetails: 'Operation Details',
      paramsJson: 'Parameters (JSON)',
      selectOperationFirst: 'Select an operation to view details',
      sendCall: 'Send Request',
      onlyActiveAllowed: 'Only active operations can be called',
    },
  },
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  components: {
    apiOperationCall: {
      title: '调用 API 操作',
      operationDetails: '操作详情',
      paramsJson: '参数 (JSON)',
      selectOperationFirst: '请先选择一个操作',
      sendCall: '发送请求',
      onlyActiveAllowed: '仅活跃的操作可以调用',
    },
  },
}, true, true)
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import type { ApiOperation, ApiOperationCallResponse } from '@/lib/apiConnectorApi'
import { formatDate } from '@/lib/dateTime'
import { Braces, ExternalLink } from 'lucide-react'

interface ApiOperationCallDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  connectorName: string
  selectedOperation: ApiOperation | null
  loading: boolean
  callParametersText: string
  onCallParametersChange: (value: string) => void
  callResult: ApiOperationCallResponse | null
  onCallOperation: () => Promise<void> | void
}

export default function ApiOperationCallDialog({
  open,
  onOpenChange,
  connectorName,
  selectedOperation,
  loading,
  callParametersText,
  onCallParametersChange,
  callResult,
  onCallOperation,
}: ApiOperationCallDialogProps) {
  const { t } = useTranslation()
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl w-[95vw] h-[85vh] overflow-hidden p-0 !grid !grid-rows-[auto_minmax(0,1fr)_auto] gap-0">
        <DialogHeader className="shrink-0 px-6 pt-6 pb-2">
          <DialogTitle>{t('components.apiOperationCall.title')}</DialogTitle>
        </DialogHeader>
        <div className="min-h-0 overflow-y-auto px-6 pb-4">
          {selectedOperation ? (
            <div className="space-y-3">
              <div className="rounded-md bg-muted p-2 text-xs">
                <p className="flex items-center gap-1 font-medium">
                  <ExternalLink className="w-3 h-3" />
                  {connectorName}
                </p>
                <p className="font-mono mt-1">
                  {selectedOperation.method} {selectedOperation.path_template}
                </p>
                <p className="text-muted-foreground mt-1">
                  {selectedOperation.summary || selectedOperation.operation_id}
                </p>
                <p className="font-mono mt-1 text-muted-foreground break-all">
                  uid: {selectedOperation.operation_uid}
                </p>
                <div className="flex items-center gap-2 mt-2">
                  <Badge variant={selectedOperation.source === 'manual' ? 'outline' : 'secondary'}>
                    {selectedOperation.source}
                  </Badge>
                  <Badge
                    variant={selectedOperation.status === 'active' ? 'outline' : 'destructive'}
                  >
                    {selectedOperation.status}
                  </Badge>
                  <Badge
                    variant={selectedOperation.last_vector_sync_error ? 'destructive' : 'outline'}
                  >
                    {selectedOperation.last_vector_sync_error
                      ? 'Vector Sync Error'
                      : 'Vector Synced'}
                  </Badge>
                </div>
                <p className="mt-2 text-muted-foreground">
                  last vector sync: {formatDate(selectedOperation.last_vector_synced_at)}
                </p>
                {selectedOperation.last_vector_sync_error && (
                  <p className="mt-1 text-red-600 break-all">
                    sync error: {selectedOperation.last_vector_sync_error}
                  </p>
                )}
              </div>

              <div className="space-y-2">
                <Label>{t('components.apiOperationCall.operationDetails')}</Label>
                <Textarea
                  rows={6}
                  value={JSON.stringify(
                    {
                      request_schema: selectedOperation.request_schema,
                      response_schema: selectedOperation.response_schema,
                      auth_requirement: selectedOperation.auth_requirement,
                      risk_level: selectedOperation.risk_level,
                    },
                    null,
                    2
                  )}
                  readOnly
                  className="font-mono text-xs resize-none"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="call-params">{t('components.apiOperationCall.paramsJson')}</Label>
                <Textarea
                  id="call-params"
                  rows={6}
                  value={callParametersText}
                  onChange={(e) => onCallParametersChange(e.target.value)}
                />
              </div>

              {callResult && (
                <div className="space-y-2">
                  <div className="flex items-center gap-2 text-sm">
                    <span className="font-medium">HTTP</span>
                    <Badge variant={callResult.error ? 'destructive' : 'outline'}>
                      {callResult.status_code || 'ERR'}
                    </Badge>
                    <span className="text-muted-foreground">
                      {callResult.elapsed_ms.toFixed(1)} ms
                    </span>
                  </div>
                  <div className="rounded-md border bg-muted/20 p-2">
                    <pre className="whitespace-pre-wrap break-all font-mono text-xs">
                      {JSON.stringify(callResult, null, 2)}
                    </pre>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">{t('components.apiOperationCall.selectOperationFirst')}</p>
          )}
        </div>

        {selectedOperation ? (
          <div className="shrink-0 border-t bg-background px-6 py-3">
            <div className="flex flex-col gap-1">
              <Button
                onClick={onCallOperation}
                disabled={loading || selectedOperation.status !== 'active'}
              >
                <Braces className="w-4 h-4 mr-2" />
                {t('components.apiOperationCall.sendCall')}
              </Button>
              {selectedOperation.status !== 'active' && (
                <p className="text-xs text-muted-foreground">{t('components.apiOperationCall.onlyActiveAllowed')}</p>
              )}
            </div>
          </div>
        ) : (
          <div className="shrink-0" />
        )}
      </DialogContent>
    </Dialog>
  )
}
