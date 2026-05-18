import { cn } from '@/lib/utils'

export type DQLevel = 1 | 2 | 3 | 4 | 5

interface DQChipProps {
  level: DQLevel
  className?: string
}

const DQ_STYLES: Record<DQLevel, string> = {
  1: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
  2: 'bg-sky-500/15 text-sky-400 border-sky-500/30',
  3: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
  4: 'bg-orange-500/15 text-orange-400 border-orange-500/30',
  5: 'bg-red-500/15 text-red-400 border-red-500/30',
}

export default function DQChip({ level, className }: DQChipProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium border',
        DQ_STYLES[level],
        className,
      )}
    >
      DQ{level}
    </span>
  )
}
