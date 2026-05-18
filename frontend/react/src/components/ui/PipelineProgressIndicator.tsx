import { Check, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'

export type PipelineStage =
  | 'queued'
  | 'ingesting'
  | 'classifying'
  | 'extracting'
  | 'scoring'
  | 'complete'
  | 'failed'

const STAGES: { key: PipelineStage; label: string }[] = [
  { key: 'ingesting', label: 'Ingesting' },
  { key: 'classifying', label: 'Classifying' },
  { key: 'extracting', label: 'Extracting' },
  { key: 'scoring', label: 'Scoring' },
  { key: 'complete', label: 'Complete' },
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

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center gap-0">
        {STAGES.map(({ key, label }, i) => {
          const done = currentIndex > i || stage === 'complete'
          const active = currentIndex === i && stage !== 'complete' && stage !== 'failed'

          return (
            <div key={key} className="flex items-center flex-1 last:flex-none">
              <div className="flex flex-col items-center gap-1.5">
                <div
                  className={cn(
                    'w-8 h-8 rounded-full flex items-center justify-center border-2 transition-colors',
                    done
                      ? 'bg-primary border-primary'
                      : active
                        ? 'border-primary bg-primary/10'
                        : 'border-border-subtle bg-surface',
                  )}
                >
                  {done ? (
                    <Check size={14} className="text-white" />
                  ) : active ? (
                    <Loader2 size={14} className="text-primary animate-spin" />
                  ) : (
                    <span className="w-2 h-2 rounded-full bg-border-subtle" />
                  )}
                </div>
                <span
                  className={cn(
                    'text-xs whitespace-nowrap',
                    done || active ? 'text-text' : 'text-text-subtle',
                  )}
                >
                  {label}
                </span>
              </div>
              {i < STAGES.length - 1 && (
                <div
                  className={cn(
                    'flex-1 h-0.5 mb-5 mx-1 transition-colors',
                    currentIndex > i ? 'bg-primary' : 'bg-border-subtle',
                  )}
                />
              )}
            </div>
          )
        })}
      </div>

      {stage !== 'complete' && stage !== 'failed' && (
        <div className="w-full h-1.5 bg-border-subtle rounded-full overflow-hidden">
          <div
            className="h-full bg-primary rounded-full transition-all duration-500"
            style={{ width: `${progress}%` }}
          />
        </div>
      )}

      {error && (
        <p className="text-sm text-danger bg-danger/10 border border-danger/20 rounded px-3 py-2">
          {error}
        </p>
      )}
    </div>
  )
}
