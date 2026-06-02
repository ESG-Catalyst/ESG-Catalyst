import { cn } from '@/lib/utils'

interface FrameworkCoverageBarProps {
  framework: string
  covered: number
  total: number
  className?: string
}

/* ── Framework metadata ─────────────────────────────────────────────────── */
const FRAMEWORK_META: Record<string, {
  color: string
  bgClass: string
  borderClass: string
  description: string
}> = {
  GRI: {
    color: 'var(--color-primary)',
    bgClass: 'bg-primary-subtle',
    borderClass: 'border-primary/25',
    description: 'Global Reporting Initiative',
  },
  FRA: {
    color: '#6366F1',
    bgClass: 'bg-[#6366F1]/10',
    borderClass: 'border-[#6366F1]/25',
    description: 'Financial Regulatory Authority',
  },
  SASB: {
    color: 'var(--color-warning)',
    bgClass: 'bg-warning-subtle',
    borderClass: 'border-warning/25',
    description: 'Sustainability Accounting Standards Board',
  },
}

/* pct → gradient class */
function barGradient(pct: number): string {
  if (pct >= 80) return 'linear-gradient(90deg, var(--color-success) 0%, #059669 100%)'
  if (pct >= 50) return 'linear-gradient(90deg, var(--color-warning) 0%, #D97706 100%)'
  return              'linear-gradient(90deg, var(--color-danger)  0%, #DC2626 100%)'
}

/* pct → label colour */
function pctColor(pct: number): string {
  if (pct >= 80) return 'var(--color-success)'
  if (pct >= 50) return 'var(--color-warning)'
  return              'var(--color-danger)'
}

export default function FrameworkCoverageBar({
  framework,
  covered,
  total,
  className,
}: FrameworkCoverageBarProps) {
  const pct  = total > 0 ? Math.round((covered / total) * 100) : 0
  const meta = FRAMEWORK_META[framework] ?? {
    color: 'var(--color-text-muted)',
    bgClass: 'bg-surface-raised',
    borderClass: 'border-border',
    description: framework,
  }

  return (
    <div
      className={cn('flex flex-col gap-2.5', className)}
      role="meter"
      aria-label={`${meta.description} coverage: ${covered} of ${total} indicators (${pct}%)`}
      aria-valuenow={pct}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      {/* Header row */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2 min-w-0">
          {/* Framework badge */}
          <span
            className={cn(
              'inline-flex items-center px-2 py-0.5 rounded-md',
              'text-xs font-bold tracking-widest border leading-none',
              'transition-colors duration-fast',
              meta.bgClass,
              meta.borderClass,
            )}
            style={{ color: meta.color }}
          >
            {framework}
          </span>
          <span className="text-xs text-text-subtle truncate hidden sm:inline">
            {meta.description}
          </span>
        </div>

        {/* Count + percentage */}
        <div className="flex items-center gap-1.5 text-xs tabular-nums shrink-0">
          <span className="font-semibold text-text">{covered}</span>
          <span className="text-text-subtle">/ {total}</span>
          <span
            className="ms-1 font-bold text-[11px] px-1.5 py-0.5 rounded"
            style={{
              color: pctColor(pct),
              background: `${pctColor(pct)}18`,
            }}
          >
            {pct}%
          </span>
        </div>
      </div>

      {/* Progress bar */}
      <div
        className="h-1.5 rounded-full bg-border-subtle overflow-hidden"
        aria-hidden="true"
      >
        <div
          className="h-full rounded-full transition-all duration-700 ease-out"
          style={{
            width: `${pct}%`,
            background: barGradient(pct),
          }}
        />
      </div>

      {/* Segment dot grid — each dot = one indicator (show when ≤ 30 total) */}
      {total > 0 && total <= 30 && (
        <div
          className="flex gap-1 flex-wrap"
          aria-label={`${covered} of ${total} indicators covered`}
          role="presentation"
        >
          {Array.from({ length: total }).map((_, i) => (
            <div
              key={i}
              className="w-2 h-2 rounded-sm transition-all duration-300"
              style={{
                background: i < covered ? meta.color : 'var(--color-border-subtle)',
                opacity:    i < covered ? 1 : 0.4,
              }}
              title={i < covered ? 'Covered' : 'Not yet disclosed'}
              aria-hidden="true"
            />
          ))}
        </div>
      )}
    </div>
  )
}
