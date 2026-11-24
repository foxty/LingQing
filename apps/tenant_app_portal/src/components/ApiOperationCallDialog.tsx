import { useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import type { ApiOperation, ApiOperationCallResponse } from '@/lib/apiConnectorApi'
import { cn } from '@/lib/utils'
import { Braces, CheckCircle2, Loader2 } from 'lucide-react'

i18n.addResourceBundle(
  'en',
  'translation',
  {
    components: {
      apiOperationCall: {
        title: 'Call API Operation',
        request: 'Request',
        response: 'Response',
        paramsJson: 'Parameters (JSON)',
        schemaDetails: 'Schemas & auth',
        emptyResponse: 'Send a request to see the response here.',
        callSucceeded: 'Succeeded',
        selectOperationFirst: 'Select an operation to view details',
        sendCall: 'Send',
        onlyActiveAllowed: 'Only active operations can be called',
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
    components: {
      apiOperationCall: {
        title: '调用 API 操作',
        request: '请求',
        response: '响应',
        paramsJson: '参数 (JSON)',
        schemaDetails: 'Schema 与鉴权',
        emptyResponse: '发送请求后，响应将显示在这里。',
        callSucceeded: '成功',
        selectOperationFirst: '请先选择一个操作',
        sendCall: '发送',
        onlyActiveAllowed: '仅活跃的操作可以调用',
      },
    },
  },
  true,
  true
)

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
  const responsePaneRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!callResult) return
    responsePaneRef.current?.scrollTo({ top: 0 })
  }, [callResult])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex h-[min(85vh,720px)] w-[95vw] max-w-5xl flex-col gap-0 overflow-hidden p-0">
        <DialogHeader className="shrink-0 space-y-2 border-b px-5 py-3 text-left">
          <DialogTitle>{t('components.apiOperationCall.title')}</DialogTitle>
          {selectedOperation ? (
            <div className="space-y-1.5">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="outline" className="font-mono">
                  {selectedOperation.method}
                </Badge>
                <code className="truncate text-sm font-medium">
                  {selectedOperation.path_template}
                </code>
                <Badge variant={selectedOperation.status === 'active' ? 'outline' : 'destructive'}>
                  {selectedOperation.status}
                </Badge>
              </div>
              <p className="truncate text-xs text-muted-foreground">
                {connectorName}
                {selectedOperation.summary || selectedOperation.operation_id
                  ? ` · ${selectedOperation.summary || selectedOperation.operation_id}`
                  : ''}
              </p>
            </div>
          ) : null}
        </DialogHeader>

        {!selectedOperation ? (
          <p className="px-5 py-8 text-sm text-muted-foreground">
            {t('components.apiOperationCall.selectOperationFirst')}
          </p>
        ) : (
          <>
            <div className="grid min-h-0 flex-1 grid-cols-1 md:grid-cols-2">
              {/* Request */}
              <section className="flex min-h-0 flex-col border-b md:border-b-0 md:border-r">
                <div className="flex shrink-0 items-center justify-between gap-2 border-b px-4 py-2">
                  <span className="text-sm font-medium">{t('components.apiOperationCall.request')}</span>
                  <Button
                    type="button"
                    size="sm"
                    className="h-8"
                    onClick={() => void onCallOperation()}
                    disabled={loading || selectedOperation.status !== 'active'}
                  >
                    {loading ? (
                      <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Braces className="mr-1.5 h-3.5 w-3.5" />
                    )}
                    {t('components.apiOperationCall.sendCall')}
                  </Button>
                </div>
                <div className="flex min-h-0 flex-1 flex-col gap-2 p-4">
                  <div className="flex shrink-0 items-center justify-between gap-2">
                    <Label htmlFor="call-params" className="text-xs text-muted-foreground">
                      {t('components.apiOperationCall.paramsJson')}
                    </Label>
                    <details className="relative text-xs">
                      <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
                        {t('components.apiOperationCall.schemaDetails')}
                      </summary>
                      <pre className="absolute right-0 z-10 mt-1 max-h-48 w-[min(100vw-2rem,22rem)] overflow-auto rounded-md border bg-popover p-2 font-mono shadow-md">
                        {JSON.stringify(
                          {
                            request_schema: selectedOperation.request_schema,
                            response_schema: selectedOperation.response_schema,
                            auth_requirement: selectedOperation.auth_requirement,
                            risk_level: selectedOperation.risk_level,
                          },
                          null,
                          2
                        )}
                      </pre>
                    </details>
                  </div>
                  {/* Native textarea: ui/Textarea wraps in a non-flexing div so flex-1 never grows. */}
                  <div className="relative min-h-0 flex-1">
                    <textarea
                      id="call-params"
                      value={callParametersText}
                      onChange={(e) => onCallParametersChange(e.target.value)}
                      spellCheck={false}
                      className={cn(
                        'absolute inset-0 h-full w-full resize-none rounded-md border border-input',
                        'bg-background px-3 py-2 font-mono text-xs leading-relaxed',
                        'ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring'
                      )}
                    />
                  </div>
                  {selectedOperation.status !== 'active' ? (
                    <p className="shrink-0 text-xs text-muted-foreground">
                      {t('components.apiOperationCall.onlyActiveAllowed')}
                    </p>
                  ) : null}
                </div>
              </section>

              {/* Response */}
              <section className="flex min-h-0 flex-col">
                <div className="flex shrink-0 items-center gap-2 border-b px-4 py-2">
                  <span className="text-sm font-medium">{t('components.apiOperationCall.response')}</span>
                  {callResult ? (
                    <>
                      <Badge variant={callResult.error ? 'destructive' : 'outline'}>
                        {callResult.status_code || 'ERR'}
                      </Badge>
                      <span className="text-xs text-muted-foreground">
                        {callResult.elapsed_ms.toFixed(1)} ms
                      </span>
                      {callResult.error ? (
                        <span className="min-w-0 truncate text-xs text-destructive">
                          {callResult.error}
                        </span>
                      ) : (
                        <span className="inline-flex min-w-0 items-center gap-1 truncate text-xs text-success">
                          <CheckCircle2 className="h-3.5 w-3.5 shrink-0" aria-hidden />
                          {t('components.apiOperationCall.callSucceeded')}
                        </span>
                      )}
                    </>
                  ) : null}
                </div>
                <div ref={responsePaneRef} className="min-h-0 flex-1 overflow-auto p-4">
                  {callResult ? (
                    <pre className="whitespace-pre-wrap break-all font-mono text-xs leading-relaxed">
                      {JSON.stringify(callResult, null, 2)}
                    </pre>
                  ) : (
                    <p className="text-sm text-muted-foreground">
                      {t('components.apiOperationCall.emptyResponse')}
                    </p>
                  )}
                </div>
              </section>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
