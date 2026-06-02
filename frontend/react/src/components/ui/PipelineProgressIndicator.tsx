import { Check, Loader2, AlertTriangle } from 'lucide-react'
import { cn } from '@/lib/utils'

export type PipelineStage =
  | 'queued'
  | 'ingesting'
  | 'chunking'
  | 'classifying'
  | 'embedding'
  | 'extracting'
  | 'scoring'
  | 'complete'
  | 'failed'

const STAGES: { key: PipelineStage; label: string; description: string }[] = [
  { key: 'ingesting',   label: 'Ingest',    description: 'Parsing document pages and tables' },
  { key: 'chunking',    label: 'Chunk',     description: 'Splitting text into semantic windows' },
  { key: 'classifying', label: 'Classify',  description: 'Filtering ESG-relevant passages' },
  { key: 'embedding',   label: 'Embed',     description: 'Generating bilingual vector embeddings' },
  { key: 'extracting',  label: 'Extract',   description: 'LLM extraction per GRI indicator' },
  { key: 'scoring',     label: 'Score',     description: 'Applying disclosure-quality methodology' },
  { key: 'complete',    label: 'Complete',  description: 'Pipeline finished' },
]

const STAGE_ORDER = STAGES.map((s) => s.key)

interface PipelineProgressIndicatorProps {
  stage: PipelineStage
  progress?: number
  error?: string | null
}

export default function PipelineProgressIndicator({
  stage,
  progress = 0,
  error,
}: PipelineProgressIndicatorProps) {
  const currentIndex = STAGE_ORDER.indexOf(stage)
  const isFailed   = stage === 'failed'
  const isComplete = stage === 'complete'

  return (
    <div className="flex flex-col gap-6" role="status" aria-live="polite">
      {/* ── Stepper ─────────────────────────────────────────────────────── */}
      <div className="flex items-start">
        {STAGES.map(({ key, label, description }, i) => {
          const done   = (!isFailed && currentIndex > i) || isComplete
          const active = !isFailed && !isComplete && currentIndex === i
          const isLast = i === STAGES.length - 1

          return (
            <div key={key} className="flex items-start flex-1 last:flex-none">
              {/* Step node + label */}
              <div className="flex flex-col items-center gap-2">
                {/* Circle */}
                <div
                  className={cn(
                    'w-8 h-8 rounded-full flex items-center justify-center',
                    'border-2 transition-all duration-base',
                    done
                      ? 'bg-primary border-primary shadow-sm'
                      : active
                        ? 'border-primary bg-primary-subtle shadow-[0_0_0_4px_var(--color-primary-subtle)]'
                        : isFailed && currentIndex === i
                          ? 'border-danger bg-danger-subtle'
                          : 'border-border bg-surface',
                  )}
                  aria-label={
                    done ? `${label}: complete`
                    : active ? `${label}: in progress`
                    : `${label}: pending`
                  }
                  title={description}
                >
                  {done ? (
                    <Check size={13} className="text-white" aria-hidden="true" />
                  ) : active ? (
                    <Loader2
                      size={13}
                      className="text-primary animate-spin"
                      aria-hidden="true"
                    />
                  ) : isFailed && currentIndex === i ? (
                    <AlertTriangle size={13} className="text-danger" aria-hidden="true" />
                  ) : (
                    <span className="w-2 h-2 rounded-full bg-border-subtle" aria-hidden="true" />
                  )}
                </div>

                {/* Step label */}
                <span
                  className={cn(
                    'text-[11px] font-medium whitespace-nowrap',
                    done || active  ? 'text-text'
                    : isFailed && currentIndex === i ? 'text-danger'
                    : 'text-text-subtle',
                  )}
                >
                  {label}
                </span>
              </div>

              {/* Connector line */}
              {!isLast && (
                <div
                  className={cn(
                    'flex-1 h-0.5 mt-4 mx-1.5 rounded-full',
                    'transition-colors duration-slow',
                    currentIndex > i && !isFailed
                      ? 'bg-primary'
                      : 'bg-border-subtle',
                  )}
                  aria-hidden="true"
                />
              )}
            </div>
          )
        })}
      </div>

      {/* ── Overall progress bar (hidden when complete / failed) ─────────── */}
      {!isComplete && !isFailed && (
        <div
          className="w-full h-1.5 bg-border-subtle rounded-full overflow-hidden"
          role="progressbar"
          aria-valuenow={progress}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`Pipeline progress: ${progress}%`}
        >
          <div
            className="h-full bg-brand-bar rounded-full transition-all duration-500 ease-out"
            style={{ width: `${Math.min(100, Math.max(0, progress))}%` }}
          />
        </div>
      )}

      {/* ── Stage description hint ───────────────────────────────────────── */}
      {!isComplete && !isFailed && (
        <p className="text-xs text-text-subtle text-center -mt-3">
          {STAGES.find((s) => s.key === stage)?.description ?? ''}
        </p>
      )}

      {/* ── Error state ──────────────────────────────────────────────────── */}
      {error && (
        <div
          className={cn(
            'flex items-start gap-2.5 px-4 py-3 rounded-lg',
            'bg-danger-subtle border border-danger/25',
          )}
          role="alert"
        >
          <AlertTriangle size={16} className="text-danger mt-0.5 shrink-0" aria-hidden="true" />
          <div className="min-w-0">
            <p className="text-sm font-medium text-danger">Pipeline failed</p>
            <p className="mt-0.5 text-xs text-danger/80 break-words">{error}</p>
          </div>
        </div>
      )}

      {/* ── Complete state ───────────────────────────────────────────────── */}
      {isComplete && !error && (
        <div
          className={cn(
            'flex items-center gap-2.5 px-4 py-3 rounded-lg',
            'bg-success-subtle border border-success/25',
          )}
          role="status"
        >
          <Check size={16} className="text-success shrink-0" aria-hidden="true" />
          <p className="text-sm font-medium text-success">Pipeline complete — metrics ready for review.</p>
        </div>
      )}
    </div>
  )
}
