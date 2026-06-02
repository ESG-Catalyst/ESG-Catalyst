import ScoreGauge from '@/components/ui/ScoreGauge'
import { cn } from '@/lib/utils'

/**
 * Branded left panel shown on the Login / Register pages.
 * Hidden below the `lg` breakpoint (the form takes full width on mobile).
 * RTL-safe: uses logical borders so the divider is always on the inner edge.
 */
export default function AuthPanel() {
  return (
    <aside
      className={cn(
        'hidden lg:flex flex-col justify-between',
        'p-10 xl:p-14',
        'bg-surface border-e border-border',
      )}
      aria-label="ESG Catalyst brand panel"
    >
      {/* Wordmark */}
      <div className="flex items-center gap-2">
        <div
          className="w-7 h-7 rounded-md flex items-center justify-center text-sm font-bold text-white shrink-0"
          style={{ background: 'var(--color-primary)' }}
          aria-hidden="true"
        >
          E
        </div>
        <span className="text-base font-semibold">
          <span style={{ color: 'var(--color-primary)' }}>ESG</span>
          <span className="text-text"> Catalyst</span>
        </span>
      </div>

      {/* Centred gauge */}
      <div className="flex flex-col items-center gap-6">
        <ScoreGauge scores={{ E: 72, S: 58, G: 65 }} overall={66} size="lg" />

        {/* Mini stat row */}
        <div className="flex items-center gap-6 text-center">
          {[
            { label: 'Indicators tracked', value: '46' },
            { label: 'Frameworks', value: 'GRI · SASB · FRA' },
          ].map((stat) => (
            <div key={stat.label}>
              <p className="text-base font-bold text-text tabular-nums">{stat.value}</p>
              <p className="text-xs text-text-subtle mt-0.5 whitespace-nowrap">{stat.label}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Regulatory quote */}
      <figure className="max-w-xs">
        <blockquote className="text-sm leading-relaxed text-text-muted mb-3">
          "ESG compliance is no longer optional for Egyptian NBFIs. FRA Decree 108 requires
          disclosure from every listed company."
        </blockquote>
        <figcaption className="text-xs text-text-subtle">
          FRA Decree 108/2021 — Financial Regulatory Authority of Egypt
        </figcaption>
      </figure>
    </aside>
  )
}
