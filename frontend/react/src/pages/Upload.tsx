import { useCallback, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { UploadCloud, FileText, X, AlertCircle } from 'lucide-react'
import { uploadDocument } from '@/api/documents'
import { runPipeline } from '@/api/pipeline'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import { usePipelineStore } from '@/store/pipeline'

const MAX_SIZE_BYTES = 50 * 1024 * 1024

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export default function Upload() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const setJob = usePipelineStore((s) => s.setJob)

  const [file, setFile] = useState<File | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const [fileError, setFileError] = useState<string | null>(null)
  const [uploadProgress, setUploadProgress] = useState<number | null>(null)
  const [serverError, setServerError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const inputRef = useRef<HTMLInputElement>(null)

  function validateFile(f: File): string | null {
    if (!f.name.toLowerCase().endsWith('.pdf')) return 'Only PDF files are accepted.'
    if (f.size > MAX_SIZE_BYTES) return `File exceeds 50 MB limit (${formatBytes(f.size)}).`
    return null
  }

  function acceptFile(f: File) {
    const err = validateFile(f)
    if (err) { setFileError(err); return }
    setFileError(null)
    setFile(f)
    setServerError(null)
    setUploadProgress(null)
  }

  const onInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (f) acceptFile(f)
  }, [])

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    const f = e.dataTransfer.files?.[0]
    if (f) acceptFile(f)
  }, [])

  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(true)
  }, [])

  const onDragLeave = useCallback(() => setDragOver(false), [])

  function removeFile() {
    setFile(null)
    setFileError(null)
    setUploadProgress(null)
    setServerError(null)
    if (inputRef.current) inputRef.current.value = ''
  }

  async function handleSubmit() {
    if (!file || submitting) return
    setSubmitting(true)
    setServerError(null)
    setUploadProgress(0)

    try {
      // Simulate upload progress while the real XHR is in flight
      const progressInterval = setInterval(() => {
        setUploadProgress((p) => (p !== null && p < 85 ? p + 12 : p))
      }, 200)

      const doc = await uploadDocument(file)
      clearInterval(progressInterval)
      setUploadProgress(100)

      await new Promise((r) => setTimeout(r, 300))

      const job = await runPipeline({ document_id: doc.document_id })
      setJob(job.job_id, doc.document_id, file.name)
      navigate(`/pipeline/${job.job_id}?doc=${doc.document_id}`)
    } catch (err: unknown) {
      setUploadProgress(null)
      setServerError(extractErrorMessage(err))
    } finally {
      setSubmitting(false)
    }
  }

  const active = dragOver || false

  return (
    <div className="p-6 max-w-2xl mx-auto">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-text">{t('upload.title')}</h1>
        <p className="text-sm text-text-muted mt-1">{t('upload.subtitle')}</p>
      </div>

      {serverError && (
        <div className="mb-5 flex items-start gap-3 px-4 py-3 rounded text-sm border"
          style={{ background: 'rgba(239,68,68,0.08)', borderColor: 'rgba(239,68,68,0.3)', color: '#EF4444' }}>
          <AlertCircle size={16} className="mt-0.5 shrink-0" />
          <span>{serverError}</span>
        </div>
      )}

      {/* Drop zone */}
      <div
        onClick={() => !file && inputRef.current?.click()}
        onDrop={onDrop}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        className={cn(
          'relative flex flex-col items-center justify-center gap-4 rounded-xl transition-all',
          'px-8 py-14 cursor-pointer select-none',
          file ? 'cursor-default' : 'cursor-pointer',
        )}
        style={{
          border: active
            ? '2px solid var(--color-primary)'
            : file
              ? '2px dashed var(--color-border-subtle)'
              : '2px dashed var(--color-primary)',
          background: active
            ? 'rgba(13,148,136,0.07)'
            : 'var(--color-surface)',
        }}
        role={file ? undefined : 'button'}
        tabIndex={file ? -1 : 0}
        onKeyDown={(e) => { if (!file && (e.key === 'Enter' || e.key === ' ')) inputRef.current?.click() }}
        aria-label="Upload PDF file"
      >
        <input
          ref={inputRef}
          type="file"
          accept=".pdf"
          className="hidden"
          onChange={onInputChange}
        />

        {!file && (
          <>
            <div
              className="w-14 h-14 rounded-full flex items-center justify-center"
              style={{ background: 'rgba(13,148,136,0.12)' }}
            >
              <UploadCloud size={26} style={{ color: 'var(--color-primary)' }} />
            </div>
            <div className="text-center">
              <p className="text-base font-semibold text-text">Drag your ESG documents here</p>
              <p className="text-sm text-text-muted mt-1">or click to browse</p>
            </div>
            <p className="text-xs text-text-subtle">PDF only · Max 50 MB</p>
          </>
        )}

        {file && (
          <div className="w-full flex items-center gap-4">
            <div
              className="w-10 h-10 rounded-lg flex items-center justify-center shrink-0"
              style={{ background: 'rgba(13,148,136,0.12)' }}
            >
              <FileText size={20} style={{ color: 'var(--color-primary)' }} />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-text truncate">{file.name}</p>
              <p className="text-xs text-text-muted mt-0.5">{formatBytes(file.size)}</p>
            </div>
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); removeFile() }}
              className="w-7 h-7 flex items-center justify-center rounded transition-colors text-text-muted hover:text-danger hover:bg-surface-raised"
              aria-label="Remove file"
            >
              <X size={15} />
            </button>
          </div>
        )}
      </div>

      {fileError && (
        <p className="mt-2 text-xs text-danger flex items-center gap-1.5">
          <AlertCircle size={13} /> {fileError}
        </p>
      )}

      {/* Upload progress bar */}
      {uploadProgress !== null && (
        <div className="mt-4">
          <div className="flex items-center justify-between text-xs text-text-muted mb-1.5">
            <span>{uploadProgress < 100 ? 'Uploading…' : 'Upload complete'}</span>
            <span style={{ fontFamily: 'var(--font-mono)' }}>{uploadProgress}%</span>
          </div>
          <div className="h-1.5 rounded-full overflow-hidden" style={{ background: 'var(--color-border-subtle)' }}>
            <div
              className="h-full rounded-full transition-all duration-300"
              style={{ width: `${uploadProgress}%`, background: 'var(--color-primary)' }}
            />
          </div>
        </div>
      )}

      {/* Submit */}
      <button
        type="button"
        onClick={handleSubmit}
        disabled={!file || submitting || !!fileError}
        className="mt-6 w-full py-2.5 text-sm font-semibold rounded flex items-center justify-center gap-2 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        style={{ background: 'var(--color-primary)', color: '#fff' }}
        onMouseEnter={(e) => { if (!e.currentTarget.disabled) e.currentTarget.style.background = 'var(--color-primary-hover)' }}
        onMouseLeave={(e) => { e.currentTarget.style.background = 'var(--color-primary)' }}
      >
        {submitting && (
          <svg className="animate-spin" width={15} height={15} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
            <path d="M21 12a9 9 0 1 1-6.219-8.56" strokeLinecap="round" />
          </svg>
        )}
        {submitting ? 'Starting analysis…' : 'Start Analysis'}
      </button>

      <p className="mt-3 text-xs text-center text-text-subtle">
        The pipeline will extract ESG metrics and score against GRI, FRA, and SASB frameworks.
        This typically takes 2–5 minutes.
      </p>
    </div>
  )
}

function extractErrorMessage(err: unknown): string {
  if (err && typeof err === 'object' && 'response' in err) {
    const r = (err as { response?: { data?: { detail?: string } } }).response
    if (r?.data?.detail) return r.data.detail
  }
  return 'Upload failed. Please try again.'
}
