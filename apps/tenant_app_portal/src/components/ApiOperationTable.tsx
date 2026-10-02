import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import PaginationBar from '@/components/PaginationBar'

i18n.addResourceBundle('en', 'translation', {
  components: {
    apiOperationTable: {
      searchPlaceholder: 'Search operations...',
      methodCol: 'Method',
      pathCol: 'Path',
      sourceCol: 'Source',
      statusCol: 'Status',
      syncCol: 'Sync',
      editOperation: 'Edit',
      deleteOperation: 'Delete',
      confirmDelete: 'Confirm Delete',
      deleteDesc: 'Are you sure you want to delete this operation?',
      confirmDeleteBtn: 'Delete',
      disableOperation: 'Disable',
      enableOperation: 'Enable',
      testOperation: 'Test',
      noOperations: 'No operations found',
      rowActions: 'Operation actions',
    },
  },
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  components: {
    apiOperationTable: {
      searchPlaceholder: '搜索操作...',
      methodCol: '方法',
      pathCol: '路径',
      sourceCol: '来源',
      statusCol: '状态',
      syncCol: '同步',
      editOperation: '编辑',
      deleteOperation: '删除',
      confirmDelete: '确认删除',
      deleteDesc: '确定要删除此操作吗？',
      confirmDeleteBtn: '删除',
      disableOperation: '停用',
      enableOperation: '启用',
      testOperation: '测试',
      noOperations: '暂无操作',
      rowActions: '操作菜单',
    },
  },
}, true, true)
import SyncStatusIndicator from '@/components/SyncStatusIndicator'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Badge } from '@/components/ui/badge'
import { Button, buttonVariants } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import type { ApiOperation } from '@/lib/apiConnectorApi'
import { MoreHorizontal, Pencil, Play, Power, Trash2 } from 'lucide-react'

interface ApiOperationTableProps {
  operations: ApiOperation[]
  selectedOperationUid?: string
  onSelectOperation: (operation: ApiOperation) => void
  onTestOperation: (operation: ApiOperation) => void
  onToggleOperationStatus: (operation: ApiOperation) => void
  onEditManualOperation: (operation: ApiOperation) => void
  onDeleteManualOperation: (operation: ApiOperation) => void
  operationsPage: number
  operationsPageSize: number
  operationsTotal: number
  operationsTotalPages: number
  onPageChange: (page: number) => void
}

export default function ApiOperationTable({
  operations,
  selectedOperationUid,
  onSelectOperation,
  onTestOperation,
  onToggleOperationStatus,
  onEditManualOperation,
  onDeleteManualOperation,
  operationsPage,
  operationsPageSize,
  operationsTotal,
  operationsTotalPages,
  onPageChange,
}: ApiOperationTableProps) {
  const { t } = useTranslation()
  const [deleteTarget, setDeleteTarget] = useState<ApiOperation | null>(null)

  return (
    <>
      <div className="overflow-hidden rounded-lg border bg-card">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="h-10 w-20">{t('components.apiOperationTable.methodCol')}</TableHead>
              <TableHead className="h-10">{t('components.apiOperationTable.pathCol')}</TableHead>
              <TableHead className="h-10 w-24">{t('components.apiOperationTable.sourceCol')}</TableHead>
              <TableHead className="h-10 w-24">{t('components.apiOperationTable.statusCol')}</TableHead>
              <TableHead className="h-10 w-28">{t('components.apiOperationTable.syncCol')}</TableHead>
              <TableHead className="h-10 w-12 text-right">{t('common.action')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {operations.map((operation) => {
              const isSelected = selectedOperationUid === operation.operation_uid
              return (
                <TableRow
                  key={operation.operation_uid}
                  className={isSelected ? 'bg-muted/60' : ''}
                  onClick={() => onSelectOperation(operation)}
                >
                  <TableCell className="py-2.5">
                    <Badge variant="secondary">{operation.method}</Badge>
                  </TableCell>
                  <TableCell className="py-2.5">
                    <div className="space-y-1">
                      <p className="font-mono text-xs break-all">{operation.path_template}</p>
                      <p className="text-xs text-muted-foreground line-clamp-2">
                        {operation.summary || operation.operation_id || 'No summary'}
                      </p>
                    </div>
                  </TableCell>
                  <TableCell className="py-2.5">
                    <Badge variant={operation.source === 'manual' ? 'outline' : 'secondary'}>
                      {operation.source}
                    </Badge>
                  </TableCell>
                  <TableCell className="py-2.5">
                    <Badge variant={operation.status === 'active' ? 'outline' : 'destructive'}>
                      {operation.status}
                    </Badge>
                  </TableCell>
                  <TableCell className="py-2.5">
                    <SyncStatusIndicator
                      syncedAt={operation.last_vector_synced_at}
                      error={operation.last_vector_sync_error}
                    />
                  </TableCell>
                  <TableCell className="py-2.5 text-right" onClick={(e) => e.stopPropagation()}>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button
                          variant="ghost"
                          className="h-11 w-11 p-0"
                          aria-label={t('components.apiOperationTable.rowActions')}
                        >
                          <MoreHorizontal className="w-4 h-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem
                          onClick={() => onTestOperation(operation)}
                        >
                          <Play className="w-4 h-4 mr-2" />
                          {t('components.apiOperationTable.testOperation')}
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          onClick={() => onToggleOperationStatus(operation)}
                        >
                          <Power className="w-4 h-4 mr-2" />
                          {operation.status === 'active'
                            ? t('components.apiOperationTable.disableOperation')
                            : t('components.apiOperationTable.enableOperation')}
                        </DropdownMenuItem>
                        {operation.source === 'manual' ? (
                          <>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem onClick={() => onEditManualOperation(operation)}>
                              <Pencil className="w-4 h-4 mr-2" />
                              {t('components.apiOperationTable.editOperation')}
                            </DropdownMenuItem>
                            <DropdownMenuItem
                              className="text-destructive focus:text-destructive"
                              onClick={() => setDeleteTarget(operation)}
                            >
                              <Trash2 className="w-4 h-4 mr-2" />
                              {t('components.apiOperationTable.deleteOperation')}
                            </DropdownMenuItem>
                          </>
                        ) : null}
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
        {operations.length === 0 && (
          <p className="text-sm text-muted-foreground py-8 text-center">
            {t('components.apiOperationTable.noOperations')}
          </p>
        )}
      </div>

      <PaginationBar
        page={operationsPage}
        pageSize={operationsPageSize}
        total={operationsTotal}
        totalPages={operationsTotalPages}
        onPageChange={onPageChange}
      />

      <AlertDialog open={deleteTarget != null} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('components.apiOperationTable.confirmDelete')}</AlertDialogTitle>
            <AlertDialogDescription>{t('components.apiOperationTable.deleteDesc')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (deleteTarget) {
                  onDeleteManualOperation(deleteTarget)
                }
                setDeleteTarget(null)
              }}
              className={buttonVariants({ variant: 'destructive' })}
            >
              {t('components.apiOperationTable.confirmDeleteBtn')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
