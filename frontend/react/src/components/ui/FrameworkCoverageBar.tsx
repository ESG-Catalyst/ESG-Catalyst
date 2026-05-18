import { cn } from '@/lib/utils'

interface FrameworkCoverageBarProps {
  framework: string
  covered: number
  total: number
  className?: string
}

const FRAMEWORK_META: Record<string, { color: string; bg: string; description: string }> = {
  GRI:  { color: '#0D9488', bg: '#0D948820', description: 'Global Reporting Initiative' },
  FRA:  { color: '#6366F1', bg: '#6366F120', description: 'Financial Regulatory Authority' },
  SASB: { color: '#F59E0B', bg: '#F59E0B20', description: 'Sustainability Accounting Standards Board' },
}

export default function FrameworkCoverageBar({
  framework,
  covered,
  total,
  className,
}: FrameworkCoverageBarProps) {
  const pct = total > 0 ? Math.round((covered / total) * 100) : 0
  const meta = FRAMEWORK_META[framework] ?? { color: '#6B7280', bg: '#6B728020', description: framework }

  return (
    <div className={cn('flex flex-col gap-2', className)}>
      {/* Header row */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span
            className="inline-flex items-center px-2 py-0.5 rounded text-xs font-bold tracking-wide"
            style={{ background: meta.bg, color: meta.color }}
          >
            {framework}
          </span>
          <span className="text-xs text-text-subtle hidden sm:inline">{meta.description}</span>
        </div>
        <div className="flex items-center gap-1.5 text-xs tabular-nums">
          <span className="font-semibold text-text">{covered}</span>
          <span className="text-text-subtle">/ {total}</span>
          <span
            className="ml-1 font-semibold"
            style={{ color: pct >= 80 ? '#10B981' : pct >= 50 ? '#F59E0B' : '#EF4444' }}
          >
            {pct}%
          </span>
        </div>
      </div>

      {/* Progress bar */}
      <div
        className="h-1.5 rounded-full overflow-hidden"
        style={{ background: 'var(--color-border-subtle)' }}
      >
        <div
          className="h-full rounded-full transition-all duration-700"
          style={{
            width: `${pct}%`,
            background:
              pct >= 80
                ? 'linear-gradient(90deg, #10B981, #059669)'
                : pct >= 50
                ? 'linear-gradient(90deg, #F59E0B, #D97706)'
                : 'linear-gradient(90deg, #EF4444, #DC2626)',
          }}
        />
      </div>

      {/* Segment dots — each dot = one indicator */}
      {total <= 30 && (
        <div className="flex gap-0.5 flex-wrap">
          {Array.from({ length: total }).map((_, i) => (
            <div
              key={i}
              className="w-2 h-2 rounded-sm transition-all duration-300"
              style={{
                background:
                  i < covered
                    ? meta.color
                    : 'var(--color-border-subtle)',
                opacity: i < covered ? 1 : 0.4,
              }}
              title={i < covered ? 'Disclosed' : 'Not yet disclosed'}
            />
          ))}
        </div>
      )}
    </div>
  )
}