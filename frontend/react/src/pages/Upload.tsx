import { useCallback, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { UploadCloud, FileText, X, AlertCircle } from 'lucide-react'
import { uploadDocument } from '@/api/documents'
import { runPipeline } from '@/api/pipeline'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import { usePipelineStore } from '@/store/pipeline'

const MAX_SIZE_BYTES = 50 * 1024 * 1024
// Silent cap — user is not told. Extra files in a pick/drop are dropped.
const MAX_FILES = 5

// Must stay in sync with backend SUPPORTED_EXTENSIONS in
// backend/app/core/ingestion/parser.py — the backend validates against
// its own set; we re-validate client-side for instant UX.
const SUPPORTED_EXTENSIONS = [
  '.pdf', '.docx', '.xlsx', '.xls', '.csv', '.txt',
  '.png', '.jpg', '.jpeg', '.tiff', '.tif', '.bmp',
] as const
const ACCEPT_ATTR = SUPPORTED_EXTENSIONS.join(',')
// Image OCR is currently stubbed in parser._parse_image; uploads succeed
// but the pipeline will surface an OCR-not-implemented error.
const IMAGE_EXTS = new Set(['.png', '.jpg', '.jpeg', '.tiff', '.tif', '.bmp'])

function getExt(name: string): string {
  const i = name.lastIndexOf('.')
  return i >= 0 ? name.slice(i).toLowerCase() : ''
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

interface SelectedFile {
  file: File
  error?: string
  warning?: string
}

function validateFile(f: File): { error?: string; warning?: string } {
  const ext = getExt(f.name)
  if (!SUPPORTED_EXTENSIONS.includes(ext as typeof SUPPORTED_EXTENSIONS[number])) {
    return { error: `Unsupported file format. Accepted: ${SUPPORTED_EXTENSIONS.join(', ')}` }
  }
  if (f.size > MAX_SIZE_BYTES) return { error: `File exceeds 50 MB limit (${formatBytes(f.size)}).` }
  if (IMAGE_EXTS.has(ext)) {
    return {
      warning:
        'Image OCR is not yet implemented. The upload will succeed but the pipeline will not extract metrics from this file.',
    }
  }
  return {}
}

export default function Upload() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const setJob = usePipelineStore((s) => s.setJob)

  const [files, setFiles] = useState<SelectedFile[]>([])
  const [dragOver, setDragOver] = useState(false)
  const [serverError, setServerError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  // null = no upload running; otherwise "X of N"
  const [uploadedCount, setUploadedCount] = useState<number | null>(null)

  const inputRef = useRef<HTMLInputElement>(null)

  // Merge newly-picked files into the existing selection, deduping by
  // (name, size) and silently capping the total at MAX_FILES. Existing
  // entries are kept so the user can add files in two clicks if they want.
  const addFiles = useCallback((picked: File[]) => {
    if (picked.length === 0) return
    setServerError(null)
    setUploadedCount(null)
    setFiles((prev) => {
      const key = (f: File) => `${f.name}|${f.size}`
      const seen = new Set(prev.map((s) => key(s.file)))
      const merged: SelectedFile[] = [...prev]
      for (const f of picked) {
        if (merged.length >= MAX_FILES) break
        if (seen.has(key(f))) continue
        seen.add(key(f))
        const { error, warning } = validateFile(f)
        merged.push({ file: f, error, warning })
      }
      return merged
    })
  }, [])

  const onInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const picked = Array.from(e.target.files ?? [])
    addFiles(picked)
    // Reset the input so the same file can be re-picked after a remove.
    if (inputRef.current) inputRef.current.value = ''
  }, [addFiles])

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    const picked = Array.from(e.dataTransfer.files ?? [])
    addFiles(picked)
  }, [addFiles])

  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(true)
  }, [])

  const onDragLeave = useCallback(() => setDragOver(false), [])

  function removeAt(index: number) {
    setFiles((prev) => prev.filter((_, i) => i !== index))
    setServerError(null)
    setUploadedCount(null)
    if (inputRef.current) inputRef.current.value = ''
  }

  const validFiles = files.filter((s) => !s.error)
  const hasAnyError = files.some((s) => s.error)
  const canSubmit = validFiles.length > 0 && !hasAnyError && !submitting
  // Pad to keep the drop-zone full-size while the user adds; once any file
  // is selected we keep showing the zone so they can add up to MAX_FILES.
  const zoneClickable = files.length < MAX_FILES

  async function handleSubmit() {
    if (!canSubmit) return
    setSubmitting(true)
    setServerError(null)
    setUploadedCount(0)

    try {
      // Upload all valid files in parallel. Each call returns
      // { document_id, filename, status }.
      const docs = await Promise.all(
        validFiles.map(async (s) => {
          const doc = await uploadDocument(s.file)
          setUploadedCount((n) => (n ?? 0) + 1)
          return { doc, original: s.file }
        }),
      )

      // Trigger the pipeline for every uploaded doc in parallel; Celery
      // queues whatever the worker can't run immediately.
      const jobs = await Promise.all(
        docs.map(async ({ doc, original }) => {
          const job = await runPipeline({ document_id: doc.document_id })
          return { job_id: job.job_id, document_id: doc.document_id, filename: original.name }
        }),
      )

      // Navigate to the first job's progress page. The pipeline store
      // currently tracks a single active job, so others run in the
      // background and surface on the dashboard / documents list.
      const first = jobs[0]
      setJob(first.job_id, first.document_id, first.filename)
      navigate(`/pipeline/${first.job_id}?doc=${first.document_id}`)
    } catch (err: unknown) {
      setUploadedCount(null)
      setServerError(extractErrorMessage(err))
    } finally {
      setSubmitting(false)
    }
  }

  const active = dragOver

  // Aggregate inline notices below the zone — show one collective image
  // warning when any of the selected files is an image. Per-file errors
  // are rendered inline on each row.
  const imageCount = files.filter((s) => !s.error && IMAGE_EXTS.has(getExt(s.file.name))).length

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

      {/* Drop zone — stays as the dropzone always (no longer collapses
          into a single-file card). The selected file list renders below. */}
      <div
        onClick={() => zoneClickable && inputRef.current?.click()}
        onDrop={onDrop}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        className={cn(
          'relative flex flex-col items-center justify-center gap-4 rounded-xl transition-all',
          'px-8 py-14 select-none',
          zoneClickable ? 'cursor-pointer' : 'cursor-not-allowed opacity-70',
        )}
        style={{
          border: active
            ? '2px solid var(--color-primary)'
            : '2px dashed var(--color-primary)',
          background: active
            ? 'rgba(13,148,136,0.07)'
            : 'var(--color-surface)',
        }}
        role={zoneClickable ? 'button' : undefined}
        tabIndex={zoneClickable ? 0 : -1}
        onKeyDown={(e) => { if (zoneClickable && (e.key === 'Enter' || e.key === ' ')) inputRef.current?.click() }}
        aria-label="Upload documents"
      >
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT_ATTR}
          multiple
          className="hidden"
          onChange={onInputChange}
        />

        <div
          className="w-14 h-14 rounded-full flex items-center justify-center"
          style={{ background: 'rgba(13,148,136,0.12)' }}
        >
          <UploadCloud size={26} style={{ color: 'var(--color-primary)' }} />
        </div>
        <div className="text-center">
          <p className="text-base font-semibold text-text">
            {files.length === 0 ? 'Drag your ESG documents here' : 'Add more documents'}
          </p>
          <p className="text-sm text-text-muted mt-1">or click to browse</p>
        </div>
        <p className="text-xs text-text-subtle">
          PDF, DOCX, XLSX, XLS, CSV, TXT, images · Max 50 MB
        </p>
      </div>

      {/* Selected-file rows */}
      {files.length > 0 && (
        <ul className="mt-4 space-y-2">
          {files.map((s, i) => (
            <li
              key={`${s.file.name}-${s.file.size}-${i}`}
              className="rounded-lg px-4 py-3"
              style={{
                background: 'var(--color-surface)',
                border: s.error
                  ? '1px solid rgba(239,68,68,0.35)'
                  : '1px solid var(--color-border-subtle)',
              }}
            >
              <div className="flex items-center gap-3">
                <div
                  className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0"
                  style={{ background: 'rgba(13,148,136,0.12)' }}
                >
                  <FileText size={18} style={{ color: 'var(--color-primary)' }} />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-text truncate">{s.file.name}</p>
                  <p className="text-xs text-text-muted mt-0.5">{formatBytes(s.file.size)}</p>
                </div>
                <button
                  type="button"
                  onClick={() => removeAt(i)}
                  disabled={submitting}
                  className="w-7 h-7 flex items-center justify-center rounded transition-colors text-text-muted hover:text-danger hover:bg-surface-raised disabled:opacity-40"
                  aria-label={`Remove ${s.file.name}`}
                >
                  <X size={15} />
                </button>
              </div>
              {s.error && (
                <p className="mt-1.5 text-xs text-danger flex items-start gap-1.5">
                  <AlertCircle size={12} className="shrink-0 mt-0.5" /> {s.error}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}

      {imageCount > 0 && (
        <p
          className="mt-3 text-xs flex items-start gap-1.5"
          style={{ color: '#F59E0B' }}
        >
          <AlertCircle size={13} className="shrink-0 mt-0.5" />
          {imageCount === 1
            ? 'Image OCR is not yet implemented. That file will upload but the pipeline will not extract metrics from it.'
            : `Image OCR is not yet implemented. ${imageCount} of your files will upload but the pipeline will not extract metrics from them.`}
        </p>
      )}

      {/* Upload progress */}
      {uploadedCount !== null && validFiles.length > 0 && (
        <div className="mt-4">
          <div className="flex items-center justify-between text-xs text-text-muted mb-1.5">
            <span>
              {uploadedCount < validFiles.length
                ? `Uploading… ${uploadedCount} of ${validFiles.length}`
                : 'Upload complete'}
            </span>
            <span style={{ fontFamily: 'var(--font-mono)' }}>
              {Math.round((uploadedCount / Math.max(validFiles.length, 1)) * 100)}%
            </span>
          </div>
          <div className="h-1.5 rounded-full overflow-hidden" style={{ background: 'var(--color-border-subtle)' }}>
            <div
              className="h-full rounded-full transition-all duration-300"
              style={{
                width: `${(uploadedCount / Math.max(validFiles.length, 1)) * 100}%`,
                background: 'var(--color-primary)',
              }}
            />
          </div>
        </div>
      )}

      {/* Submit */}
      <button
        type="button"
        onClick={handleSubmit}
        disabled={!canSubmit}
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
        {submitting
          ? 'Starting analysis…'
          : validFiles.length <= 1
            ? 'Start Analysis'
            : `Start Analysis (${validFiles.length} files)`}
      </button>

      <p className="mt-3 text-xs text-center text-text-subtle">
        The pipeline will extract ESG metrics and score against GRI, FRA, and SASB frameworks.
        This typically takes 2–5 minutes per file.
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
