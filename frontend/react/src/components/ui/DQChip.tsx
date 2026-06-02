import { cn } from '@/lib/utils'

export type DQLevel = 1 | 2 | 3 | 4 | 5

interface DQChipProps {
  level: DQLevel
  /** Show an abbreviated label instead of "DQn" */
  label?: string
  className?: string
}

/*
  DQ scale (lower = better quality):
  1 — Fully disclosed    (green)
  2 — Quantitative + citation  (teal)
  3 — Quantitative, no citation (amber)
  4 — Qualitative only   (orange)
  5 — Missing / rejected (red)
*/
const DQ_STYLES: Record<DQLevel, { chip: string; dot: string }> = {
  1: { chip: 'bg-success-subtle  text-success  border-success/25',  dot: 'bg-success'  },
  2: { chip: 'bg-info-subtle     text-info     border-info/25',     dot: 'bg-info'     },
  3: { chip: 'bg-warning-subtle  text-warning  border-warning/25',  dot: 'bg-warning'  },
  4: { chip: 'bg-orange-500/10   text-orange-400 border-orange-500/25', dot: 'bg-orange-400' },
  5: { chip: 'bg-danger-subtle   text-danger   border-danger/25',   dot: 'bg-danger'   },
}

const DQ_ARIA: Record<DQLevel, string> = {
  1: 'Data quality 1 — fully disclosed',
  2: 'Data quality 2 — quantitative with citation',
  3: 'Data quality 3 — quantitative, no citation',
  4: 'Data quality 4 — qualitative only',
  5: 'Data quality 5 — missing or rejected',
}

export default function DQChip({ level, label, className }: DQChipProps) {
  const { chip, dot } = DQ_STYLES[level]
  const displayLabel = label ?? `DQ${level}`

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 px-2 py-0.5 rounded',
        'text-xs font-semibold border leading-none select-none',
        'transition-colors duration-fast',
        chip,
        className,
      )}
      aria-label={DQ_ARIA[level]}
      title={DQ_ARIA[level]}
    >
      <span className={cn('w-1.5 h-1.5 rounded-full shrink-0', dot)} aria-hidden="true" />
      {displayLabel}
    </span>
  )
}
