import { useEffect, useRef, useState } from 'react'
import { useParams, useSearchParams, useNavigate, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import {
  CheckCircle2,
  XCircle,
  FileInput,
  Scissors,
  Layers,
  BrainCircuit,
  Cpu,
  BarChart2,
  Flag,
  AlertTriangle,
  Clock,
  Ban,
} from 'lucide-react'
import { getPipelineStatus } from '@/api/pipeline'
import { usePipelineStore } from '@/store/pipeline'
import { shortRef } from '@/lib/format'
import { useTranslation } from 'react-i18next'

// ─── Step definitions ─────────────────────────────────────────────────────────

type TFn = (k: string, o?: Record<string, unknown>) => string

const STEPS = [
  { id: 'ingestion',   label: 'pipeline.step_ingestion',     icon: FileInput,    hint: 'pipeline.hint_ingestion',      estimateSec: 30  },
  { id: 'chunking',    label: 'pipeline.step_chunking',       icon: Scissors,     hint: 'pipeline.hint_chunking',       estimateSec: 15  },
  { id: 'classifying', label: 'pipeline.step_classification', icon: BrainCircuit, hint: 'pipeline.hint_classification', estimateSec: 900 },
  { id: 'embedding',   label: 'pipeline.step_embedding',      icon: Layers,       hint: 'pipeline.hint_embedding',      estimateSec: 60  },
  { id: 'extracting',  label: 'pipeline.step_extraction',     icon: Cpu,          hint: 'pipeline.hint_extraction',     estimateSec: 900 },
  { id: 'scoring',     label: 'pipeline.step_scoring',        icon: BarChart2,    hint: 'pipeline.hint_scoring',        estimateSec: 30  },
  { id: 'complete',    label: 'pipeline.step_complete',       icon: Flag,         hint: 'pipeline.hint_complete',       estimateSec: 0   },
] as const

type StepId = (typeof STEPS)[number]['id']

function stepIndex(stage: string): number {
  const idx = STEPS.findIndex((s) => s.id === stage)
  return idx === -1 ? 0 : idx
}

// ─── Chunk grid (classification visualiser) ───────────────────────────────────
// Shows a grid of small squares filling up as the classifier processes chunks.
// We animate the fill count based on elapsed time since classification started.

const GRID_COLS = 20
const GRID_TOTAL = 80 // visual representation — 80 squares ≈ "many chunks"

function ChunkGrid({
  active,
  filledCount,
  total,
}: {
  active: boolean
  filledCount: number
  total: number
}) {
  const { t } = useTranslation()
  const filled = Math.min(filledCount, total)
  const pct = total > 0 ? Math.round((filled / total) * 100) : 0

  return (
    <div className="mt-3 mb-1">
      <div className="flex items-center justify-between text-xs text-text-muted mb-2">
        <span>{t('pipeline.chunks_classified')}</span>
        <span style={{ fontFamily: 'var(--font-mono)' }}>
          {filled}/{total} ({pct}%)
        </span>
      </div>
      <div
        className="grid gap-1"
        style={{ gridTemplateColumns: `repeat(${GRID_COLS}, minmax(0, 1fr))` }}
      >
        {Array.from({ length: total }).map((_, i) => {
          const isFilled = i < filled
          return (
            <motion.div
              key={i}
              className="rounded-sm"
              style={{ height: 8 }}
              animate={{
                background: isFilled
                  ? 'var(--color-primary)'
                  : active && i === filled
                  ? '#F59E0B'
                  : 'var(--color-border)',
                opacity: isFilled ? 1 : active && i === filled ? 0.8 : 0.4,
              }}
              transition={{ duration: 0.15, delay: isFilled ? 0 : 0 }}
            />
          )
        })}
      </div>
      <div className="flex items-center gap-4 mt-2 text-xs text-text-subtle">
        <span className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-sm inline-block" style={{ background: 'var(--color-primary)' }} />
          {t('pipeline.esg_relevant')}
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-sm inline-block" style={{ background: 'var(--color-border)' }} />
          {t('pipeline.not_relevant')}
        </span>
        {active && (
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-sm inline-block" style={{ background: '#F59E0B' }} />
            {t('pipeline.processing')}
          </span>
        )}
      </div>
    </div>
  )
}

// ─── Time estimate ────────────────────────────────────────────────────────────

function useElapsed(running: boolean): number {
  const [elapsed, setElapsed] = useState(0)
  const startRef = useRef<number | null>(null)

  useEffect(() => {
    if (running) {
      startRef.current = startRef.current ?? Date.now()
      const id = setInterval(() => {
        setElapsed(Math.floor((Date.now() - startRef.current!) / 1000))
      }, 1000)
      return () => clearInterval(id)
    } else {
      startRef.current = null
      setElapsed(0)
    }
  }, [running])

  return elapsed
}

function formatSec(s: number): string {
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  const rem = s % 60
  return rem > 0 ? `${m}m ${rem}s` : `${m}m`
}

function TimeEstimate({ stepId, elapsed }: { stepId: StepId; elapsed: number }) {
  const { t } = useTranslation()
  const step = STEPS.find((s) => s.id === stepId)
  if (!step || step.estimateSec === 0) return null
  const remaining = Math.max(0, step.estimateSec - elapsed)
  return (
    <div className="flex items-center gap-1.5 text-xs text-text-muted mt-1.5">
      <Clock size={11} />
      <span>
        {elapsed > 0
          ? t('pipeline.elapsed_remaining', { elapsed: formatSec(elapsed), remaining: formatSec(remaining) })
          : t('pipeline.remaining_only', { remaining: formatSec(remaining) })}
      </span>
    </div>
  )
}

// ─── LLM error classifier ─────────────────────────────────────────────────────

function classifyError(errorMsg: string | null, t: TFn): {
  type: 'credit_limit' | 'fallback_exhausted' | 'abort' | 'generic'
  title: string
  detail: string
  canRetry: boolean
} {
  if (!errorMsg) return { type: 'generic', title: t('pipeline.error_generic'), detail: t('pipeline.detail_generic'), canRetry: true }

  const lower = errorMsg.toLowerCase()

  if (
    lower.includes('402') ||
    lower.includes('insufficient credits') ||
    lower.includes('key limit exceeded') ||
    lower.includes('payment required')
  ) {
    return { type: 'credit_limit', title: t('pipeline.error_credit_limit'), detail: t('pipeline.detail_credit_limit'), canRetry: true }
  }

  if (
    lower.includes('both models failed') ||
    (lower.includes('fallback') && lower.includes('failed')) ||
    lower.includes('all models exhausted')
  ) {
    return { type: 'abort', title: t('pipeline.error_all_models_unavailable'), detail: t('pipeline.detail_all_models'), canRetry: false }
  }

  if (lower.includes('rate limit') || lower.includes('429') || lower.includes('too many requests')) {
    return { type: 'credit_limit', title: t('pipeline.error_rate_limit'), detail: t('pipeline.detail_rate_limit'), canRetry: true }
  }

  if (lower.includes('timeout') || lower.includes('timed out')) {
    return { type: 'generic', title: t('pipeline.error_timeout'), detail: t('pipeline.detail_timeout'), canRetry: true }
  }

  return { type: 'generic', title: t('pipeline.error_generic'), detail: errorMsg, canRetry: true }
}

// ─── Step row ─────────────────────────────────────────────────────────────────

function StepRow({
  step,
  state,
  hint,
  elapsed,
}: {
  step: (typeof STEPS)[number]
  state: 'waiting' | 'active' | 'complete' | 'failed'
  hint?: string
  elapsed?: number
}) {
  const { t } = useTranslation()
  const Icon = step.icon

  const iconColor =
    state === 'complete'
      ? '#10B981'
      : state === 'active'
        ? 'var(--color-primary)'
        : state === 'failed'
          ? '#EF4444'
          : 'var(--color-text-subtle)'

  // live chunk grid for classifying step
  const isClassifying = step.id === 'classifying' && state === 'active'
  // Animate filled squares based on elapsed time — assume ~10 chunks/second on CPU
  const chunksFilled = isClassifying && elapsed != null
    ? Math.min(GRID_TOTAL, Math.round((elapsed / (step.estimateSec || 900)) * GRID_TOTAL))
    : 0

  return (
    <div className="flex items-start gap-4">
      {/* Icon column */}
      <div className="flex flex-col items-center">
        <div
          className="w-9 h-9 rounded-full flex items-center justify-center shrink-0 transition-colors"
          style={{
            background: state === 'waiting' ? 'var(--color-surface-raised)' : `${iconColor}18`,
            border: `1.5px solid ${state === 'waiting' ? 'var(--color-border)' : iconColor}`,
          }}
        >
          {state === 'complete' ? (
            <CheckCircle2 size={17} style={{ color: iconColor }} />
          ) : state === 'failed' ? (
            <XCircle size={17} style={{ color: iconColor }} />
          ) : state === 'active' ? (
            <motion.div
              animate={{ opacity: [1, 0.4, 1] }}
              transition={{ duration: 1.2, repeat: Infinity, ease: 'easeInOut' }}
            >
              <Icon size={17} style={{ color: iconColor }} />
            </motion.div>
          ) : (
            <Icon size={17} style={{ color: iconColor }} />
          )}
        </div>
        {/* Connector line (not on last step) */}
        {step.id !== 'complete' && (
          <div
            className="w-px flex-1 mt-1"
            style={{
              minHeight: 28,
              background: state === 'complete' ? '#10B981' : 'var(--color-border)',
            }}
          />
        )}
      </div>

      {/* Text column */}
      <div className="pb-6 flex-1 min-w-0">
        <p
          className="text-sm leading-tight"
          style={{
            fontWeight: state === 'active' ? 600 : 400,
            color:
              state === 'waiting'
                ? 'var(--color-text-subtle)'
                : state === 'active'
                  ? 'var(--color-text)'
                  : state === 'complete'
                    ? '#10B981'
                    : '#EF4444',
          }}
        >
          {t(step.label)}
        </p>
        {state === 'active' && hint && (
          <p className="text-xs text-text-muted mt-0.5">{hint}</p>
        )}
        {state === 'active' && elapsed != null && step.estimateSec > 0 && (
          <TimeEstimate stepId={step.id} elapsed={elapsed} />
        )}
        {/* Chunk grid for classifying step */}
        {isClassifying && (
          <ChunkGrid active={true} filledCount={chunksFilled} total={GRID_TOTAL} />
        )}
        {state === 'failed' && hint && (
          <p className="text-xs mt-0.5" style={{ color: '#EF4444' }}>{hint}</p>
        )}
      </div>
    </div>
  )
}

// ─── Stats panel ──────────────────────────────────────────────────────────────

function StatRow({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex items-center justify-between py-2.5" style={{ borderBottom: '1px solid var(--color-border)' }}>
      <span className="text-xs text-text-muted">{label}</span>
      <span className="text-xs font-semibold text-text" style={{ fontFamily: 'var(--font-mono)' }}>
        {value}
      </span>
    </div>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function PipelineProgress() {
  const { t } = useTranslation()
  const { jobId } = useParams<{ jobId: string }>()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const { documentId: storedDocId, documentName: storedDocName, setJob } = usePipelineStore()
  const documentId = searchParams.get('doc') ?? storedDocId ?? ''

  // Persist job context so navigating away and back restores state
  useEffect(() => {
    if (jobId && documentId) setJob(jobId, documentId)
  }, [jobId, documentId, setJob])

  // Track when the current active step started so we can show elapsed time
  const [lastStage, setLastStage] = useState<string>('')

  const { data: status, error } = useQuery({
    queryKey: ['pipeline-status', jobId],
    queryFn: () => getPipelineStatus(jobId!),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const stage = query.state.data?.stage
      if (stage === 'complete' || stage === 'failed') return false
      return 2000
    },
  })

  const stage = status?.stage ?? 'queued'
  const progress = status?.progress ?? 0
  const apiError = status?.error ?? null

  // Reset step timer when stage changes
  useEffect(() => {
    if (stage !== lastStage) {
      setLastStage(stage)
    }
  }, [stage, lastStage])

  const elapsed = useElapsed(stage !== 'complete' && stage !== 'failed' && stage !== 'queued')

  const currentIdx = stepIndex(stage)
  const isFailed = stage === 'failed'
  const isComplete = stage === 'complete'

  // Classify the error for friendly messaging
  const errInfo = isFailed ? classifyError(apiError, t) : null

  async function retryPipeline() {
    if (!documentId) return
    try {
      const { runPipeline } = await import('@/api/pipeline')
      const job = await runPipeline({ document_ids: [documentId] })
      navigate(`/pipeline/${job.job_id}?doc=${documentId}`)
    } catch {
      // noop — user will see page reload
    }
  }

  if (error) {
    return (
      <div className="p-6 max-w-2xl mx-auto" role="alert">
        <div
          className="flex items-start gap-3 px-4 py-4 rounded-xl"
          style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.3)' }}
        >
          <AlertTriangle size={18} style={{ color: '#EF4444' }} className="mt-0.5 shrink-0" aria-hidden="true" />
          <div>
            <p className="text-sm font-semibold" style={{ color: '#EF4444' }}>{t('pipeline.could_not_load_status')}</p>
            <p className="text-xs text-text-muted mt-1">{t('pipeline.job_id_label')}: <span style={{ fontFamily: 'var(--font-mono)' }}>{jobId}</span></p>
            <p className="text-xs text-text-subtle mt-2">{t('pipeline.could_not_load_hint')}</p>
          </div>
        </div>
      </div>
    )
  }

  // Show a human-readable document name if available from the pipeline store
  const docLabel = storedDocName
    ? storedDocName
    : documentId
      ? `${documentId.slice(0, 8)}…`
      : null

  return (
    <div className="p-6 max-w-3xl mx-auto">
      {/* Header */}
      <div className="mb-8">
        <p className="text-xs font-semibold uppercase tracking-widest text-text-muted mb-1">{t('pipeline.eyebrow')}</p>
        <h1 className="text-2xl font-semibold text-text">
          {isComplete ? t('pipeline.analysis_complete') : isFailed ? t('pipeline.analysis_failed') : t('pipeline.analysis_in_progress')}
        </h1>
        {docLabel && (
          <p className="text-sm text-text-muted mt-1 truncate max-w-sm" title={storedDocName ?? documentId}>
            <span className="font-medium text-text-subtle">{t('pipeline.document_label')}:</span> {docLabel}
            {jobId && <span className="text-text-subtle"> · {t('pipeline.job_label')} {shortRef(jobId)}</span>}
          </p>
        )}
      </div>

      <div className="grid lg:grid-cols-[1fr_220px] gap-6">
        {/* Left — steps + progress */}
        <div>
          {/* Overall progress bar */}
          <div className="mb-6">
            <div className="flex items-center justify-between text-xs text-text-muted mb-2">
              <span>{t('pipeline.overall_progress')}</span>
              <span style={{ fontFamily: 'var(--font-mono)' }}>{progress}%</span>
            </div>
            <div className="h-2 rounded-full overflow-hidden" style={{ background: 'var(--color-border-subtle)' }}>
              <motion.div
                className="h-full rounded-full"
                style={{ background: isFailed ? '#EF4444' : 'var(--color-primary)' }}
                animate={{ width: `${progress}%` }}
                transition={{ duration: 0.5, ease: 'easeOut' }}
              />
            </div>
          </div>

          {/* Steps */}
          <div>
            {STEPS.map((step, i) => {
              let state: 'waiting' | 'active' | 'complete' | 'failed' = 'waiting'
              if (isFailed && i === currentIdx) state = 'failed'
              else if (i < currentIdx) state = 'complete'
              else if (i === currentIdx && !isComplete) state = 'active'
              else if (isComplete) state = 'complete'

              const hint =
                state === 'active'
                  ? step.hint
                  : state === 'failed' && i === currentIdx && apiError
                    ? apiError
                    : undefined

              return (
                <StepRow
                  key={step.id}
                  step={step}
                  state={state}
                  hint={hint}
                  elapsed={state === 'active' ? elapsed : undefined}
                />
              )
            })}
          </div>
        </div>

        {/* Right — live stats */}
        <div>
          <div
            className="rounded-lg p-4 sticky top-6"
            style={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)' }}
          >
            <p className="text-xs font-semibold uppercase tracking-widest text-text-muted mb-1">
              {t('pipeline.pipeline_info')}
            </p>
            <div>
              <StatRow label={t('pipeline.stage')} value={t(`pipeline.${stage}`, { defaultValue: stage })} />
              <StatRow label={t('pipeline.progress')} value={`${progress}%`} />
              <StatRow
                label={t('pipeline.step_elapsed')}
                value={elapsed > 0 && stage !== 'complete' && stage !== 'failed' ? formatSec(elapsed) : '—'}
              />
              <StatRow
                label={t('pipeline.est_remaining')}
                value={(() => {
                  const step = STEPS.find((s) => s.id === stage)
                  if (!step || step.estimateSec === 0 || stage === 'complete' || stage === 'failed') return '—'
                  return `~${formatSec(Math.max(0, step.estimateSec - elapsed))}`
                })()}
              />
            </div>
            <p className="text-xs text-text-subtle mt-3">
              {stage === 'classifying'
                ? t('pipeline.info_classifying')
                : stage === 'extracting'
                  ? t('pipeline.info_extracting')
                  : t('pipeline.info_polling')}
            </p>
          </div>
        </div>
      </div>

      {/* Complete state */}
      <AnimatePresence>
        {isComplete && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 12 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            transition={{ duration: 0.4, ease: 'easeOut' }}
            className="mt-8 rounded-xl p-8 flex flex-col items-center text-center"
            style={{ background: 'rgba(16,185,129,0.07)', border: '1px solid rgba(16,185,129,0.25)' }}
            role="status"
            aria-live="polite"
            aria-label="Analysis complete"
          >
            <motion.div
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              transition={{ type: 'spring', stiffness: 260, damping: 20, delay: 0.1 }}
            >
              <CheckCircle2 size={52} style={{ color: '#10B981' }} aria-hidden="true" />
            </motion.div>
            <p className="text-lg font-semibold text-text mt-4">{t('pipeline.analysis_complete')}</p>
            <p className="text-sm text-text-muted mt-1">{t('pipeline.metrics_ready')}</p>
            {documentId && (
              <Link
                to={`/results/${documentId}`}
                className="mt-6 inline-flex items-center gap-2 px-6 py-2.5 text-sm font-semibold rounded-lg transition-colors focus-visible:ring-2 ring-offset-2"
                style={{ background: '#10B981', color: '#fff', '--tw-ring-color': '#10B981' } as React.CSSProperties}
                onMouseEnter={(e) => (e.currentTarget.style.background = '#059669')}
                onMouseLeave={(e) => (e.currentTarget.style.background = '#10B981')}
                aria-label="Review extracted metrics"
              >
                {t('pipeline.review_metrics')}
                <CheckCircle2 size={14} aria-hidden="true" />
              </Link>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Failed state */}
      <AnimatePresence>
        {isFailed && errInfo && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35 }}
            className="mt-8 rounded-xl p-6 flex flex-col gap-4"
            style={{ background: 'rgba(239,68,68,0.07)', border: '1px solid rgba(239,68,68,0.25)' }}
            role="alert"
            aria-live="assertive"
          >
            <div className="flex items-start gap-3">
              {errInfo.type === 'abort' ? (
                <Ban size={24} style={{ color: '#EF4444' }} className="shrink-0 mt-0.5" aria-hidden="true" />
              ) : (
                <XCircle size={24} style={{ color: '#EF4444' }} className="shrink-0 mt-0.5" aria-hidden="true" />
              )}
              <div>
                <p className="text-base font-semibold" style={{ color: '#EF4444' }}>{errInfo.title}</p>
                <p className="text-sm text-text-muted mt-1 leading-relaxed max-w-lg">{errInfo.detail}</p>
              </div>
            </div>

            {/* Context-aware tip */}
            {errInfo.type === 'credit_limit' && (
              <div
                className="rounded-lg px-4 py-3 text-xs leading-relaxed"
                style={{ background: 'rgba(245,158,11,0.1)', border: '1px solid rgba(245,158,11,0.3)', color: '#F59E0B' }}
              >
                {t('pipeline.credit_tip')}
              </div>
            )}
            {errInfo.type === 'abort' && (
              <div
                className="rounded-lg px-4 py-3 text-xs leading-relaxed"
                style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', color: '#EF4444' }}
              >
                {t('pipeline.abort_tip')}
              </div>
            )}

            <div className="flex items-center gap-3 flex-wrap">
              {errInfo.canRetry && (
                <button
                  onClick={retryPipeline}
                  disabled={!documentId}
                  className="px-5 py-2.5 text-sm font-semibold rounded-lg transition-colors disabled:opacity-40 focus-visible:ring-2 ring-primary ring-offset-1"
                  style={{ background: 'var(--color-primary)', color: '#fff' }}
                  onMouseEnter={(e) => { if (!e.currentTarget.disabled) e.currentTarget.style.background = 'var(--color-primary-hover)' }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = 'var(--color-primary)' }}
                >
                  {t('pipeline.retry')}
                </button>
              )}
              <a
                href="mailto:support@esg-catalyst.tech"
                className="text-sm text-text-muted hover:text-text transition-colors focus-visible:ring-2 ring-primary rounded px-1"
              >
                {t('pipeline.contact_support')}
              </a>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}