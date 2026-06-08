import { useCallback, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { UploadCloud, FileText, X, AlertCircle, CheckCircle2, Info } from 'lucide-react'
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

type TFn = (k: string, o?: Record<string, unknown>) => string

function validateFile(f: File, t: TFn): { error?: string; warning?: string } {
  const ext = getExt(f.name)
  if (!SUPPORTED_EXTENSIONS.includes(ext as typeof SUPPORTED_EXTENSIONS[number])) {
    return { error: t('upload.unsupported_format', { formats: SUPPORTED_EXTENSIONS.join(', ') }) }
  }
  if (f.size > MAX_SIZE_BYTES) return { error: t('upload.file_too_large', { size: formatBytes(f.size) }) }
  if (IMAGE_EXTS.has(ext)) {
    return { warning: t('upload.image_ocr_warning_single') }
  }
  return {}
}

// Format badge for a file extension — groups by type
function FileTypeBadge({ ext }: { ext: string }) {
  const groups: Record<string, string> = {
    '.pdf': 'PDF',
    '.docx': 'DOCX',
    '.xlsx': 'XLSX',
    '.xls': 'XLS',
    '.csv': 'CSV',
    '.txt': 'TXT',
  }
  const label = groups[ext] ?? ext.replace('.', '').toUpperCase()
  const isImage = IMAGE_EXTS.has(ext)
  return (
    <span
      className="text-xs font-semibold px-1.5 py-0.5 rounded"
      style={{
        background: isImage ? 'rgba(245,158,11,0.1)' : 'rgba(13,148,136,0.1)',
        color: isImage ? '#F59E0B' : 'var(--color-primary)',
        fontFamily: 'var(--font-mono)',
      }}
    >
      {label}
    </span>
  )
}

function extractErrorMessage(err: unknown, t: TFn): string {
  if (err && typeof err === 'object' && 'response' in err) {
    const r = (err as { response?: { data?: { detail?: string } } }).response
    if (r?.data?.detail) return r.data.detail
  }
  return t('upload.upload_failed')
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
        const { error, warning } = validateFile(f, t)
        merged.push({ file: f, error, warning })
      }
      return merged
    })
  }, [t])

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

      // Run ONE pooled pipeline over the whole set: every file is
      // chunked / classified / embedded together, then a single extraction
      // pass runs with per-metric source attribution (46 LLM calls, not 46×N).
      const documentIds = docs.map(({ doc }) => doc.document_id)
      const job = await runPipeline({ document_ids: documentIds })

      // Track the primary document for navigation; the Results page reads the
      // whole Report (all the set's metrics) via any of its documents.
      const primary = docs[0]
      const setLabel =
        docs.length === 1
          ? primary.original.name
          : `${primary.original.name} +${docs.length - 1} more`
      setJob(job.job_id, job.document_id, setLabel)
      navigate(`/pipeline/${job.job_id}?doc=${job.document_id}`)
    } catch (err: unknown) {
      setUploadedCount(null)
      setServerError(extractErrorMessage(err, t))
    } finally {
      setSubmitting(false)
    }
  }

  const active = dragOver

  // Aggregate inline notices below the zone — show one collective image
  // warning when any of the selected files is an image. Per-file errors
  // are rendered inline on each row.
  const imageCount = files.filter((s) => !s.error && IMAGE_EXTS.has(getExt(s.file.name))).length

  const uploadProgress =
    uploadedCount !== null && validFiles.length > 0
      ? Math.round((uploadedCount / Math.max(validFiles.length, 1)) * 100)
      : 0
  const isUploadComplete = uploadedCount !== null && uploadedCount >= validFiles.length

  return (
    <div className="p-6 max-w-2xl mx-auto">
      {/* Header */}
      <div className="mb-8">
        <p className="text-xs font-semibold uppercase tracking-widest text-text-muted mb-1">
          Document Upload
        </p>
        <h1 className="text-2xl font-semibold text-text">{t('upload.title')}</h1>
        <p className="text-sm text-text-muted mt-1">{t('upload.subtitle')}</p>
      </div>

      {/* Server error banner */}
      {serverError && (
        <div
          className="mb-5 flex items-start gap-3 px-4 py-3 rounded-lg text-sm border"
          role="alert"
          style={{ background: 'rgba(239,68,68,0.08)', borderColor: 'rgba(239,68,68,0.3)', color: '#EF4444' }}
        >
          <AlertCircle size={16} className="mt-0.5 shrink-0" aria-hidden="true" />
          <span>{serverError}</span>
        </div>
      )}

      {/* Drop zone */}
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
            ? 'rgba(13,148,136,0.09)'
            : 'var(--color-surface)',
          boxShadow: active ? '0 0 0 4px rgba(13,148,136,0.08)' : undefined,
          transition: 'border-color 0.15s, background 0.15s, box-shadow 0.15s',
        }}
        role={zoneClickable ? 'button' : undefined}
        tabIndex={zoneClickable ? 0 : -1}
        onKeyDown={(e) => { if (zoneClickable && (e.key === 'Enter' || e.key === ' ')) inputRef.current?.click() }}
        aria-label={files.length === 0 ? 'Upload documents — click or drag files here' : 'Add more documents — click or drag files here'}
      >
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT_ATTR}
          multiple
          className="sr-only"
          onChange={onInputChange}
          aria-hidden="true"
          tabIndex={-1}
        />

        <motion.div
          animate={{ scale: active ? 1.1 : 1 }}
          transition={{ duration: 0.2 }}
          className="w-14 h-14 rounded-full flex items-center justify-center"
          style={{ background: active ? 'rgba(13,148,136,0.18)' : 'rgba(13,148,136,0.10)' }}
        >
          <UploadCloud
            size={26}
            style={{ color: 'var(--color-primary)' }}
            aria-hidden="true"
          />
        </motion.div>

        <div className="text-center">
          <p className="text-base font-semibold text-text">
            {active
              ? t('upload.drop_active')
              : files.length === 0
                ? t('upload.drop_hint')
                : t('upload.add_more')}
          </p>
          <p className="text-sm text-text-muted mt-1">
            {active ? '' : t('upload.browse')}
          </p>
        </div>

        <div className="flex flex-wrap items-center justify-center gap-1.5" aria-label="Accepted file types">
          {['PDF', 'DOCX', 'XLSX', 'CSV', 'TXT'].map((fmt) => (
            <span
              key={fmt}
              className="text-xs px-2 py-0.5 rounded"
              style={{
                background: 'rgba(13,148,136,0.08)',
                color: 'var(--color-primary)',
                border: '1px solid rgba(13,148,136,0.15)',
                fontFamily: 'var(--font-mono)',
              }}
            >
              {fmt}
            </span>
          ))}
          <span className="text-xs text-text-subtle">· {t('upload.max_size_note')}</span>
        </div>

        {/* File count badge when files are selected */}
        {files.length > 0 && (
          <span
            className="absolute top-3 end-3 text-xs font-semibold px-2 py-0.5 rounded-full"
            style={{ background: 'var(--color-primary)', color: '#fff' }}
            aria-label={`${files.length} file${files.length > 1 ? 's' : ''} selected`}
          >
            {files.length}/{MAX_FILES}
          </span>
        )}
      </div>

      {/* Selected-file rows */}
      {files.length > 0 && (
        <ul className="mt-4 space-y-2" aria-label="Selected files">
          {files.map((s, i) => (
            <li
              key={`${s.file.name}-${s.file.size}-${i}`}
              className="rounded-lg px-4 py-3 transition-all"
              style={{
                background: 'var(--color-surface)',
                border: s.error
                  ? '1px solid rgba(239,68,68,0.35)'
                  : s.warning
                    ? '1px solid rgba(245,158,11,0.35)'
                    : '1px solid var(--color-border-subtle)',
              }}
            >
              <div className="flex items-center gap-3">
                <div
                  className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0"
                  style={{
                    background: s.error
                      ? 'rgba(239,68,68,0.1)'
                      : s.warning
                        ? 'rgba(245,158,11,0.1)'
                        : 'rgba(13,148,136,0.10)',
                  }}
                  aria-hidden="true"
                >
                  <FileText
                    size={18}
                    style={{
                      color: s.error ? '#EF4444' : s.warning ? '#F59E0B' : 'var(--color-primary)',
                    }}
                  />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="text-sm font-medium text-text truncate">{s.file.name}</p>
                    <FileTypeBadge ext={getExt(s.file.name)} />
                  </div>
                  <p className="text-xs text-text-muted mt-0.5">{formatBytes(s.file.size)}</p>
                </div>
                {/* Status icon — valid files show a checkmark */}
                {!s.error && !s.warning && (
                  <CheckCircle2
                    size={14}
                    style={{ color: '#10B981' }}
                    className="shrink-0"
                    aria-label="File valid"
                  />
                )}
                <button
                  type="button"
                  onClick={() => removeAt(i)}
                  disabled={submitting}
                  className="w-7 h-7 flex items-center justify-center rounded transition-colors text-text-muted hover:text-danger hover:bg-surface-raised disabled:opacity-40 focus-visible:ring-2 ring-primary"
                  aria-label={`Remove ${s.file.name}`}
                >
                  <X size={15} aria-hidden="true" />
                </button>
              </div>
              {s.error && (
                <p className="mt-2 text-xs text-danger flex items-start gap-1.5" role="alert">
                  <AlertCircle size={12} className="shrink-0 mt-0.5" aria-hidden="true" />
                  {s.error}
                </p>
              )}
              {s.warning && !s.error && (
                <p className="mt-2 text-xs flex items-start gap-1.5" style={{ color: '#F59E0B' }}>
                  <Info size={12} className="shrink-0 mt-0.5" aria-hidden="true" />
                  {s.warning}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}

      {/* Collective image warning — only shown when warnings not already
          inline on each row (i.e. more than one image file selected) */}
      {imageCount > 1 && (
        <div
          className="mt-3 text-xs flex items-start gap-2 px-3 py-2 rounded-lg"
          role="status"
          style={{
            background: 'rgba(245,158,11,0.08)',
            border: '1px solid rgba(245,158,11,0.25)',
            color: '#F59E0B',
          }}
        >
          <Info size={13} className="shrink-0 mt-0.5" aria-hidden="true" />
          <span>
            {t('upload.image_ocr_warning_multi', { count: imageCount })}
          </span>
        </div>
      )}

      {/* Upload progress */}
      {uploadedCount !== null && validFiles.length > 0 && (
        <div className="mt-4" role="status" aria-label={`Upload progress: ${uploadProgress}%`}>
          <div className="flex items-center justify-between text-xs text-text-muted mb-1.5">
            <span className="flex items-center gap-1.5">
              {isUploadComplete && (
                <CheckCircle2 size={12} style={{ color: '#10B981' }} aria-hidden="true" />
              )}
              {isUploadComplete
                ? t('upload.upload_complete_starting')
                : t('upload.uploading', { done: uploadedCount, total: validFiles.length })}
            </span>
            <span style={{ fontFamily: 'var(--font-mono)' }}>
              {uploadProgress}%
            </span>
          </div>
          <div
            className="h-1.5 rounded-full overflow-hidden"
            style={{ background: 'var(--color-border-subtle)' }}
          >
            <div
              className="h-full rounded-full transition-all duration-300"
              style={{
                width: `${uploadProgress}%`,
                background: isUploadComplete ? '#10B981' : 'var(--color-primary)',
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
        className="mt-6 w-full py-3 text-sm font-semibold rounded-lg flex items-center justify-center gap-2 transition-colors disabled:opacity-50 disabled:cursor-not-allowed focus-visible:ring-2 ring-primary ring-offset-2"
        style={{ background: 'var(--color-primary)', color: '#fff' }}
        onMouseEnter={(e) => { if (!e.currentTarget.disabled) e.currentTarget.style.background = 'var(--color-primary-hover)' }}
        onMouseLeave={(e) => { e.currentTarget.style.background = 'var(--color-primary)' }}
        aria-busy={submitting}
      >
        {submitting && (
          <svg
            className="animate-spin"
            width={15}
            height={15}
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
            aria-hidden="true"
          >
            <path d="M21 12a9 9 0 1 1-6.219-8.56" strokeLinecap="round" />
          </svg>
        )}
        {submitting
          ? t('upload.button_running')
          : validFiles.length <= 1
            ? t('upload.button')
            : t('upload.button_multi', { count: validFiles.length })}
      </button>

      <p className="mt-3 text-xs text-center text-text-subtle">
        {t('upload.pipeline_note')}
      </p>
    </div>
  )
}
