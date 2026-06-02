import { cn } from '@/lib/utils'
import StatusPill from './StatusPill'
import type { StatusValue } from './StatusPill'

export interface MetricRow {
  id: string
  gri_code: string
  label: string
  value?: number | null
  unit?: string | null
  confidence: number
  status: StatusValue
  pillar?: string | null
}

interface MetricTableProps {
  rows?: MetricRow[]
  onApprove?: (id: string) => void
  onReject?: (id: string) => void
  /** Show pillar column (default: auto-shows when any row has a pillar) */
  showPillar?: boolean
}

/* Pillar badge colours */
const PILLAR_STYLES: Record<string, string> = {
  E: 'bg-success-subtle text-success border-success/20',
  S: 'bg-info-subtle    text-info    border-info/20',
  G: 'bg-[#A78BFA]/10  text-[#A78BFA] border-[#A78BFA]/20',
}

export default function MetricTable({
  rows = [],
  onApprove,
  onReject,
  showPillar,
}: MetricTableProps) {
  const hasPillar = showPillar ?? rows.some((r) => r.pillar)
  const hasActions = !!(onApprove || onReject)

  return (
    <div
      className={cn(
        'rounded-lg border border-border overflow-hidden',
        'shadow-sm bg-surface',
      )}
    >
      <div className="overflow-x-auto">
        <table className="w-full text-sm" role="grid">
          <thead>
            <tr className="bg-surface-raised border-b border-border">
              <th
                scope="col"
                className="text-start ps-4 pe-3 py-3 text-xs font-semibold text-text-muted tracking-wide uppercase whitespace-nowrap"
              >
                GRI / Code
              </th>
              {hasPillar && (
                <th
                  scope="col"
                  className="text-start px-3 py-3 text-xs font-semibold text-text-muted tracking-wide uppercase"
                >
                  Pillar
                </th>
              )}
              <th
                scope="col"
                className="text-start px-3 py-3 text-xs font-semibold text-text-muted tracking-wide uppercase"
              >
                Indicator
              </th>
              <th
                scope="col"
                className="text-start px-3 py-3 text-xs font-semibold text-text-muted tracking-wide uppercase whitespace-nowrap"
              >
                Value
              </th>
              <th
                scope="col"
                className="text-start px-3 py-3 text-xs font-semibold text-text-muted tracking-wide uppercase whitespace-nowrap"
              >
                Confidence
              </th>
              <th
                scope="col"
                className="text-start px-3 py-3 text-xs font-semibold text-text-muted tracking-wide uppercase"
              >
                Status
              </th>
              {hasActions && (
                <th
                  scope="col"
                  className="text-start ps-3 pe-4 py-3 text-xs font-semibold text-text-muted tracking-wide uppercase"
                >
                  Actions
                </th>
              )}
            </tr>
          </thead>

          <tbody>
            {rows.length === 0 && (
              <tr>
                <td
                  colSpan={5 + (hasPillar ? 1 : 0) + (hasActions ? 1 : 0)}
                  className="px-4 py-12 text-center"
                >
                  <div className="flex flex-col items-center gap-2">
                    <span className="text-2xl select-none" aria-hidden="true">—</span>
                    <p className="text-sm text-text-muted">No metrics extracted yet.</p>
                    <p className="text-xs text-text-subtle">Run the pipeline to extract ESG indicators.</p>
                  </div>
                </td>
              </tr>
            )}

            {rows.map((row, idx) => (
              <tr
                key={row.id}
                className={cn(
                  'border-b border-border last:border-0 group',
                  'transition-colors duration-fast',
                  'hover:bg-surface-raised/60',
                  idx % 2 === 0 ? 'bg-surface' : 'bg-bg/30',
                )}
              >
                {/* GRI code */}
                <td className="ps-4 pe-3 py-3 font-mono text-xs text-text-muted whitespace-nowrap">
                  {row.gri_code}
                </td>

                {/* Pillar */}
                {hasPillar && (
                  <td className="px-3 py-3">
                    {row.pillar ? (
                      <span
                        className={cn(
                          'inline-flex items-center px-1.5 py-0.5 rounded text-xs font-bold border',
                          PILLAR_STYLES[row.pillar] ?? 'bg-surface-raised text-text-muted border-border',
                        )}
                        title={
                          row.pillar === 'E' ? 'Environmental'
                          : row.pillar === 'S' ? 'Social'
                          : 'Governance'
                        }
                      >
                        {row.pillar}
                      </span>
                    ) : (
                      <span className="text-text-subtle">—</span>
                    )}
                  </td>
                )}

                {/* Label */}
                <td className="px-3 py-3 text-text max-w-xs">
                  <span className="line-clamp-2">{row.label}</span>
                </td>

                {/* Value */}
                <td className="px-3 py-3 font-mono text-xs tabular-nums text-text whitespace-nowrap">
                  {row.value != null
                    ? <span className="font-medium">{row.value}{row.unit ? <span className="text-text-muted ms-1">{row.unit}</span> : null}</span>
                    : <span className="text-text-subtle">—</span>}
                </td>

                {/* Confidence */}
                <td className="px-3 py-3">
                  <ConfidenceBar value={row.confidence} />
                </td>

                {/* Status */}
                <td className="px-3 py-3">
                  <StatusPill status={row.status} />
                </td>

                {/* Actions */}
                {hasActions && (
                  <td className="ps-3 pe-4 py-3">
                    <div className="flex gap-1.5">
                      {onApprove && (
                        <button
                          onClick={() => onApprove(row.id)}
                          aria-label={`Approve ${row.label}`}
                          className={cn(
                            'text-xs px-2.5 py-1 rounded border font-medium',
                            'bg-success-subtle text-success border-success/25',
                            'hover:bg-success/20 focus-visible:ring-2 ring-success',
                            'transition-colors duration-fast',
                          )}
                        >
                          Approve
                        </button>
                      )}
                      {onReject && (
                        <button
                          onClick={() => onReject(row.id)}
                          aria-label={`Reject ${row.label}`}
                          className={cn(
                            'text-xs px-2.5 py-1 rounded border font-medium',
                            'bg-danger-subtle text-danger border-danger/25',
                            'hover:bg-danger/20 focus-visible:ring-2 ring-danger',
                            'transition-colors duration-fast',
                          )}
                        >
                          Reject
                        </button>
                      )}
                    </div>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Row count footer */}
      {rows.length > 0 && (
        <div className="px-4 py-2 border-t border-border bg-surface-raised flex items-center justify-between">
          <p className="text-xs text-text-subtle">
            {rows.length} indicator{rows.length !== 1 ? 's' : ''}
          </p>
          <p className="text-xs text-text-subtle">
            {rows.filter((r) => r.status === 'approved').length} approved
            {' · '}
            {rows.filter((r) => r.status === 'missing').length} missing
          </p>
        </div>
      )}
    </div>
  )
}

/* ── Confidence bar sub-component ───────────────────────────────────────── */
function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.min(100, Math.max(0, Math.round(value * 100)))
  const colorClass =
    pct >= 80 ? 'bg-success'
    : pct >= 60 ? 'bg-warning'
    : 'bg-danger'

  const ariaLabel = `Confidence: ${pct}%`

  return (
    <div className="flex items-center gap-2" aria-label={ariaLabel} title={ariaLabel}>
      <div
        className="w-14 h-1.5 rounded-full bg-border-subtle overflow-hidden shrink-0"
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div
          className={cn('h-full rounded-full transition-all duration-slow', colorClass)}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs text-text-muted tabular-nums w-8">{pct}%</span>
    </div>
  )
}
