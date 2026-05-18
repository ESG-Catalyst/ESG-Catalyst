import ScoreGauge from '@/components/ui/ScoreGauge'

export default function AuthPanel() {
  return (
    <div
      className="hidden lg:flex flex-col justify-between p-12"
      style={{
        background: 'var(--color-surface)',
        borderRight: '1px solid var(--color-border)',
      }}
    >
      {/* Wordmark */}
      <div className="text-base font-semibold">
        <span style={{ color: 'var(--color-primary)' }}>ESG</span>
        <span className="text-text"> Catalyst</span>
      </div>

      {/* Gauge centred */}
      <div className="flex flex-col items-center gap-10">
        <ScoreGauge scores={{ E: 72, S: 58, G: 65 }} overall={66} size="lg" />
      </div>

      {/* Quote */}
      <blockquote className="max-w-xs">
        <p className="text-sm leading-relaxed text-text-muted mb-4">
          "ESG compliance is no longer optional for Egyptian NBFIs. FRA Decree 108 requires
          disclosure from every listed company."
        </p>
        <footer className="text-xs text-text-subtle">
          FRA Decree 108/2021 — Financial Regulatory Authority of Egypt
        </footer>
      </blockquote>
    </div>
  )
}
