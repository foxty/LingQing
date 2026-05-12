import { useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'

i18n.addResourceBundle('en', 'translation', {
  components: {
    csvUploadDialog: {
      title: 'Upload CSV',
      description: 'Upload files to {{name}} (max {{max}} files)',
      unsupportedType: 'Unsupported file type. Supported: {{types}}',
      fileTooLarge: 'File exceeds 10MB limit',
      maxFilesError: 'Maximum {{max}} files allowed',
      dragDrop: 'Drag & drop files here, or click to browse',
      supportedFormats: 'CSV, XLSX, XLS (max {{max}} files)',
      tableNameRequired: 'Table Name',
      tableCreated: 'Table "{{name}}" created',
      noFilesToUpload: 'No files to upload',
      allFilesNeedTableName: 'All files need a table name',
      tableNameHint: 'Must start with a letter and contain only lowercase letters, numbers, and underscores',
      uploadFailed: 'Upload failed',
      uploadSuccess: '{{count}} file(s) uploaded successfully',
      uploadPartial: '{{count}} file(s) failed to upload',
      total: 'Total: {{count}}',
      successful: '{{count}} success',
      failed: '{{count}} failed',
      pending: '{{count}} pending',
      cancel: 'Cancel',
      finish: 'Upload',
      uploading: 'Uploading...',
    },
  },
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  components: {
    csvUploadDialog: {
      title: '上传 CSV',
      description: '上传文件到 {{name}}（最多 {{max}} 个文件）',
      unsupportedType: '不支持的文件类型。支持: {{types}}',
      fileTooLarge: '文件超过 10MB 限制',
      maxFilesError: '最多允许 {{max}} 个文件',
      dragDrop: '拖拽文件到此处，或点击浏览',
      supportedFormats: 'CSV, XLSX, XLS（最多 {{max}} 个文件）',
      tableNameRequired: '表名',
      tableCreated: '表 "{{name}}" 已创建',
      noFilesToUpload: '没有文件可上传',
      allFilesNeedTableName: '所有文件都需要表名',
      tableNameHint: '必须以字母开头，仅包含小写字母、数字和下划线',
      uploadFailed: '上传失败',
      uploadSuccess: '{{count}} 个文件上传成功',
      uploadPartial: '{{count}} 个文件上传失败',
      total: '总计: {{count}}',
      successful: '{{count}} 成功',
      failed: '{{count}} 失败',
      pending: '{{count}} 待处理',
      cancel: '取消',
      finish: '上传',
      uploading: '上传中...',
    },
  },
}, true, true)
import { useAssets } from '@/hooks/useDataSources'
import { useNotification } from '@/hooks/useNotification'
import type { DataSource } from '@/lib/dataSourceApi'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Progress } from '@/components/ui/progress'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Upload, FileSpreadsheet, X, CheckCircle, AlertCircle } from 'lucide-react'

interface CSVUploadDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  dataSource: DataSource
  onSuccess?: () => void
}

interface FileItem {
  file: File
  tableName: string
  status: 'pending' | 'uploading' | 'success' | 'error'
  error?: string
}

const SUPPORTED_FILE_TYPES = ['.csv', '.xlsx', '.xls']
const ACCEPT_FILE_TYPES = SUPPORTED_FILE_TYPES.join(',')
const MAX_FILES = 10
const MAX_FILE_SIZE = 10 * 1024 * 1024 // 10MB

export default function CSVUploadDialog({
  open,
  onOpenChange,
  dataSource,
  onSuccess,
}: CSVUploadDialogProps) {
  const { t } = useTranslation()
  const { uploadCsvFile } = useAssets(dataSource.id)
  const { showSuccess, showError } = useNotification()

  const [files, setFiles] = useState<FileItem[]>([])
  const [dragActive, setDragActive] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [globalError, setGlobalError] = useState('')

  const resetState = () => {
    setFiles([])
    setUploading(false)
    setGlobalError('')
    setDragActive(false)
  }

  const handleClose = () => {
    if (!uploading) {
      resetState()
      onOpenChange(false)
    }
  }

  const validateFile = (file: File): string | null => {
    const extension = file.name.toLowerCase().match(/\.[^.]+$/)?.[0]
    if (!extension || !SUPPORTED_FILE_TYPES.includes(extension)) {
      return t('components.csvUploadDialog.unsupportedType', { types: SUPPORTED_FILE_TYPES.join(', ') })
    }

    if (file.size > MAX_FILE_SIZE) {
      return t('components.csvUploadDialog.fileTooLarge')
    }

    return null
  }

  const generateTableName = (fileName: string): string => {
    // Remove extension and convert to snake_case
    const nameWithoutExt = fileName.replace(/\.[^.]+$/, '')
    return nameWithoutExt
      .toLowerCase()
      .replace(/[^a-z0-9_]/g, '_')
      .replace(/_{2,}/g, '_')
      .replace(/^_|_$/g, '')
  }

  const handleFilesSelect = useCallback(
    (selectedFiles: FileList | File[]) => {
      const fileArray = Array.from(selectedFiles)

      // Check max files limit
      if (files.length + fileArray.length > MAX_FILES) {
        setGlobalError(t('components.csvUploadDialog.maxFilesError', { max: MAX_FILES }))
        return
      }

      const newFiles: FileItem[] = []

      for (const file of fileArray) {
        const error = validateFile(file)
        if (error) {
          newFiles.push({
            file,
            tableName: generateTableName(file.name),
            status: 'error',
            error,
          })
        } else {
          newFiles.push({
            file,
            tableName: generateTableName(file.name),
            status: 'pending',
          })
        }
      }

      setFiles((prev) => [...prev, ...newFiles])
      setGlobalError('')
    },
    [files.length]
  )

  const handleDrag = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true)
    } else if (e.type === 'dragleave') {
      setDragActive(false)
    }
  }, [])

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      e.stopPropagation()
      setDragActive(false)

      if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        handleFilesSelect(e.dataTransfer.files)
      }
    },
    [handleFilesSelect]
  )

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      handleFilesSelect(e.target.files)
    }
  }

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index))
  }

  const updateTableName = (index: number, newName: string) => {
    setFiles((prev) =>
      prev.map((item, i) => (i === index ? { ...item, tableName: newName } : item))
    )
  }

  const handleUploadAll = async () => {
    // Validate all files
    const pendingFiles = files.filter((f) => f.status === 'pending' || f.status === 'error')

    if (pendingFiles.length === 0) {
      setGlobalError(t('components.csvUploadDialog.noFilesToUpload'))
      return
    }

    // Check for empty or invalid table names
    for (const fileItem of pendingFiles) {
      if (!fileItem.tableName.trim()) {
        setGlobalError(t('components.csvUploadDialog.allFilesNeedTableName'))
        return
      }
      if (!/^[a-z][a-z0-9_]*$/.test(fileItem.tableName)) {
        setGlobalError(t('components.csvUploadDialog.tableNameHint'))
        return
      }
    }

    setUploading(true)
    setGlobalError('')

    // Track upload results
    let successfulUploads = 0
    let failedUploads = 0

    // Upload files sequentially
    for (let i = 0; i < files.length; i++) {
      const fileItem = files[i]
      if (fileItem.status !== 'pending') continue

      // Update status to uploading
      setFiles((prev) =>
        prev.map((item, idx) => (idx === i ? { ...item, status: 'uploading' as const } : item))
      )

      try {
        await uploadCsvFile(fileItem.file, fileItem.tableName)

        // Update status to success
        setFiles((prev) =>
          prev.map((item, idx) => (idx === i ? { ...item, status: 'success' as const } : item))
        )
        successfulUploads++
      } catch (error: any) {
        // Update status to error
        setFiles((prev) =>
          prev.map((item, idx) =>
            idx === i
              ? {
                  ...item,
                  status: 'error' as const,
                  error: error.response?.data?.detail || t('components.csvUploadDialog.uploadFailed'),
                }
              : item
          )
        )
        failedUploads++
      }
    }

    setUploading(false)

    // Show result notifications
    if (successfulUploads > 0) {
      showSuccess(t('components.csvUploadDialog.uploadSuccess', { count: successfulUploads }))
    }
    if (failedUploads > 0) {
      showError(t('components.csvUploadDialog.uploadPartial', { count: failedUploads }))
    }

    // If at least one file was successfully uploaded, trigger refresh
    if (successfulUploads > 0) {
      setTimeout(() => {
        handleClose()
        onSuccess?.()
      }, 1500)
    }
  }

  const pendingCount = files.filter((f) => f.status === 'pending').length
  const successCount = files.filter((f) => f.status === 'success').length
  const errorCount = files.filter((f) => f.status === 'error').length
  const canUpload = pendingCount > 0 && !uploading

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[600px] max-h-[80vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>{t('components.csvUploadDialog.title')}</DialogTitle>
          <DialogDescription>
            {t('components.csvUploadDialog.description', { name: dataSource.name, max: MAX_FILES })}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4 flex-1 overflow-hidden flex flex-col">
          {/* File Drop Zone */}
          <div
            className={`relative border-2 border-dashed rounded-lg p-6 text-center transition-colors ${
              dragActive ? 'border-primary bg-primary/5' : 'border-border hover:border-primary/50'
            } ${uploading ? 'pointer-events-none opacity-50' : ''}`}
            onDragEnter={handleDrag}
            onDragLeave={handleDrag}
            onDragOver={handleDrag}
            onDrop={handleDrop}
          >
            <input
              type="file"
              accept={ACCEPT_FILE_TYPES}
              multiple
              onChange={handleFileInput}
              disabled={uploading || files.length >= MAX_FILES}
              className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
            />

            <div className="space-y-2">
              <Upload className="w-12 h-12 mx-auto text-muted-foreground" />
              <div>
                <p className="font-medium">{t('components.csvUploadDialog.dragDrop')}</p>
                <p className="text-sm text-muted-foreground mt-1">
                  {t('components.csvUploadDialog.supportedFormats', { max: MAX_FILES })}
                </p>
              </div>
            </div>
          </div>

          {/* Files List */}
          {files.length > 0 && (
            <div className="flex-1 overflow-auto space-y-2 border rounded-lg p-3 bg-muted/20">
              {files.map((fileItem, index) => (
                <div key={index} className="bg-background border rounded-lg p-3 space-y-2">
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-start gap-2 flex-1 min-w-0">
                      <FileSpreadsheet
                        className={`w-5 h-5 flex-shrink-0 mt-0.5 ${
                          fileItem.status === 'success'
                            ? 'text-green-600'
                            : fileItem.status === 'error'
                              ? 'text-red-600'
                              : fileItem.status === 'uploading'
                                ? 'text-foreground'
                                : 'text-muted-foreground'
                        }`}
                      />
                      <div className="flex-1 min-w-0">
                        <p className="font-medium text-sm truncate">{fileItem.file.name}</p>
                        <p className="text-xs text-muted-foreground">
                          {(fileItem.file.size / 1024).toFixed(1)} KB
                        </p>
                      </div>
                    </div>

                    {fileItem.status === 'success' && (
                      <CheckCircle className="w-5 h-5 text-green-600 flex-shrink-0" />
                    )}
                    {fileItem.status === 'error' && (
                      <AlertCircle className="w-5 h-5 text-red-600 flex-shrink-0" />
                    )}
                    {fileItem.status === 'uploading' && (
                      <div className="w-5 h-5 border-2 border-primary border-t-transparent rounded-full animate-spin flex-shrink-0" />
                    )}
                    {(fileItem.status === 'pending' || fileItem.status === 'error') &&
                      !uploading && (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => removeFile(index)}
                          className="h-6 w-6 p-0 flex-shrink-0"
                        >
                          <X className="w-4 h-4" />
                        </Button>
                      )}
                  </div>

                  {/* Table Name Input */}
                  {(fileItem.status === 'pending' || fileItem.status === 'error') && (
                    <div className="space-y-1">
                        <Label htmlFor={`tableName-${index}`} className="text-xs">
                          {t('components.csvUploadDialog.tableNameRequired')} <span className="text-destructive">*</span>
                        </Label>
                      <Input
                        id={`tableName-${index}`}
                        value={fileItem.tableName}
                        onChange={(e) => updateTableName(index, e.target.value)}
                        placeholder="sales_data"
                        disabled={uploading}
                        className="h-8 text-sm"
                      />
                    </div>
                  )}

                  {fileItem.status === 'success' && (
                    <Alert className="py-2 bg-green-50 border-green-200">
                      <AlertDescription className="text-xs text-green-800">
                        {t('components.csvUploadDialog.tableCreated', { name: fileItem.tableName })}
                      </AlertDescription>
                    </Alert>
                  )}

                  {fileItem.status === 'error' && fileItem.error && (
                    <Alert variant="destructive" className="py-2">
                      <AlertDescription className="text-xs">{fileItem.error}</AlertDescription>
                    </Alert>
                  )}

                  {fileItem.status === 'uploading' && (
                    <Progress value={undefined} className="h-1" />
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Summary */}
          {files.length > 0 && (
            <div className="flex items-center gap-4 text-sm text-muted-foreground">
              <span>{t('components.csvUploadDialog.total', { count: files.length })}</span>
              {successCount > 0 && <span className="text-green-600">{t('components.csvUploadDialog.successful', { count: successCount })}</span>}
              {errorCount > 0 && <span className="text-red-600">{t('components.csvUploadDialog.failed', { count: errorCount })}</span>}
              {pendingCount > 0 && <span>{t('components.csvUploadDialog.pending', { count: pendingCount })}</span>}
            </div>
          )}

          {/* Global Error Message */}
          {globalError && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{globalError}</AlertDescription>
            </Alert>
          )}

          {/* Helper Text */}
          {files.length === 0 && (
            <p className="text-xs text-muted-foreground text-center">
              {t('components.csvUploadDialog.tableNameHint')}
            </p>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={handleClose} disabled={uploading}>
            {successCount === files.length && files.length > 0 ? t('components.csvUploadDialog.finish') : t('components.csvUploadDialog.cancel')}
          </Button>
          <Button onClick={handleUploadAll} disabled={!canUpload}>
            {uploading ? t('components.csvUploadDialog.uploading') : `${t('components.csvUploadDialog.finish')} (${pendingCount})`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
