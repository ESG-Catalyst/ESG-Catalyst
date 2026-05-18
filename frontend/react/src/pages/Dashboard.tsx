import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import {
  Upload,
  CheckCircle2,
  FileText,
  AlertCircle,
  Clock,
  ArrowRight,
  BarChart2,
} from 'lucide-react'
import ScoreGauge from '@/components/ui/ScoreGauge'
import FrameworkCoverageBar from '@/components/ui/FrameworkCoverageBar'
import StatusPill, { type StatusValue } from '@/components/ui/StatusPill'
import { listDocuments } from '@/api/documents'
import { getMetrics, type MetricDTO } from '@/api/metrics'
import { listReports, generateReport } from '@/api/reports'
import { useAuthStore } from '@/store/auth'

// ─── Skeleton ─────────────────────────────────────────────────────────────────

function Skeleton({ className = '' }: { className?: string }) {
  return (
    <div
      className={`rounded animate-pulse ${className}`}
      style={{ background: 'var(--color-surface-raised)' }}
    />
  )
}

// ─── Card wrapper ─────────────────────────────────────────────────────────────

function Card({
  children,
  className = '',
  style = {},
}: {
  children: React.ReactNode
  className?: string
  style?: React.CSSProperties
}) {
  return (
    <div
      className={`rounded-lg p-5 ${className}`}
      style={{
        background: 'var(--color-surface)',
        border: '1px solid var(--color-border)',
        ...style,
      }}
    >
      {children}
    </div>
  )
}

// ─── Score overview card ──────────────────────────────────────────────────────

function TIER_LABEL(score: number): string {
  if (score >= 75) return 'Leading'
  if (score >= 55) return 'Established'
  if (score >= 35) return 'Developing'
  return 'Laggard'
}

function TIER_COLOR(tier: string): string {
  if (tier === 'Leading') return '#10B981'
  if (tier === 'Established') return '#0D9488'
  if (tier === 'Developing') return '#F59E0B'
  return '#EF4444'
}

function ScoreCard({ metrics }: { metrics: MetricDTO[] }) {
  const eMetrics = metrics.filter((m) => m.pillar === 'E' && m.value != null)
  const sMetrics = metrics.filter((m) => m.pillar === 'S' && m.value != null)
  const gMetrics = metrics.filter((m) => m.pillar === 'G' && m.value != null)

  const avgConf = (arr: MetricDTO[]) =>
    arr.length ? Math.round((arr.reduce((s, m) => s + m.confidence, 0) / arr.length) * 100) : 0

  const scores = {
    E: avgConf(eMetrics),
    S: avgConf(sMetrics),
    G: avgConf(gMetrics),
  }
  const overall = Math.round((scores.E + scores.S + scores.G) / 3)
  const tier = TIER_LABEL(overall)

  return (
    <Card>
      <p className="text-xs font-semibold uppercase tracking-widest text-text-muted mb-4">
        ESG Score Overview
      </p>
      <div className="flex justify-center">
        <ScoreGauge scores={scores} overall={overall} size="md" />
      </div>
      <div className="mt-4 flex justify-center">
        <span
          className="inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold"
          style={{
            background: `${TIER_COLOR(tier)}20`,
            color: TIER_COLOR(tier),
            border: `1px solid ${TIER_COLOR(tier)}40`,
          }}
        >
          {tier}
        </span>
      </div>
    </Card>
  )
}

// ─── Framework coverage card ──────────────────────────────────────────────────

function CoverageCard({ metrics }: { metrics: MetricDTO[] }) {
  const disclosed = (fw: string) =>
    metrics.filter(
      (m) =>
        (fw === 'GRI'
          ? m.gri_code
          : fw === 'FRA'
            ? m.fra_code
            : m.sasb_code) &&
        (m.status === 'extracted' || m.status === 'approved'),
    ).length

  const GRI_TOTAL = 24
  const FRA_TOTAL = 1
  const SASB_TOTAL = 21

  return (
    <Card>
      <p className="text-xs font-semibold uppercase tracking-widest text-text-muted mb-4">
        Framework Coverage
      </p>
      <div className="flex flex-col gap-5">
        <FrameworkCoverageBar framework="GRI" covered={disclosed('GRI')} total={GRI_TOTAL} />
        <FrameworkCoverageBar framework="FRA" covered={disclosed('FRA')} total={FRA_TOTAL} />
        <FrameworkCoverageBar framework="SASB" covered={disclosed('SASB')} total={SASB_TOTAL} />
      </div>
      <p className="mt-4 text-xs text-text-subtle">
        {metrics.filter((m) => m.status === 'extracted' || m.status === 'approved').length} of 46
        indicators disclosed
      </p>
    </Card>
  )
}

// ─── Activity feed ────────────────────────────────────────────────────────────

interface ActivityItem {
  icon: React.ElementType
  color: string
  text: string
  time: string
}

function timeAgo(dateStr: string): string {
  const diff = (Date.now() - new Date(dateStr).getTime()) / 1000
  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

function ActivityFeed({
  documents,
  metrics,
}: {
  documents: { filename: string; status: string; uploaded_at?: string }[]
  metrics: MetricDTO[]
}) {
  const items: ActivityItem[] = []

  documents.slice(0, 2).forEach((doc) => {
    if (doc.uploaded_at) {
      items.push({
        icon: Upload,
        color: '#38BDF8',
        text: `"${doc.filename}" uploaded`,
        time: timeAgo(doc.uploaded_at),
      })
    }
    if (doc.status === 'complete' || doc.status === 'extracted') {
      items.push({
        icon: BarChart2,
        color: '#0D9488',
        text: `Pipeline completed for "${doc.filename}"`,
        time: doc.uploaded_at ? timeAgo(doc.uploaded_at) : '—',
      })
    }
  })

  const approved = metrics.filter((m) => m.status === 'approved').length
  if (approved > 0) {
    items.push({
      icon: CheckCircle2,
      color: '#10B981',
      text: `${approved} metric${approved > 1 ? 's' : ''} approved`,
      time: 'recently',
    })
  }

  const missing = metrics.filter((m) => m.status === 'missing').length
  if (missing > 0) {
    items.push({
      icon: AlertCircle,
      color: '#F59E0B',
      text: `${missing} indicator${missing > 1 ? 's' : ''} not yet disclosed`,
      time: 'pending',
    })
  }

  const feed = items.slice(0, 5)

  return (
    <Card>
      <p className="text-xs font-semibold uppercase tracking-widest text-text-muted mb-4">
        Recent Activity
      </p>
      {feed.length === 0 ? (
        <p className="text-sm text-text-subtle">No activity yet.</p>
      ) : (
        <ul className="flex flex-col gap-3">
          {feed.map((item, i) => (
            <li key={i} className="flex items-start gap-3">
              <item.icon size={15} className="mt-0.5 shrink-0" style={{ color: item.color }} />
              <div className="flex-1 min-w-0">
                <p className="text-sm text-text leading-snug">{item.text}</p>
              </div>
              <span className="text-xs text-text-subtle shrink-0 flex items-center gap-1">
                <Clock size={11} />
                {item.time}
              </span>
            </li>
          ))}
        </ul>
      )}
      <Link
        to="/results"
        className="mt-4 flex items-center gap-1 text-xs text-primary hover:underline"
      >
        View all activity <ArrowRight size={12} />
      </Link>
    </Card>
  )
}

// ─── Quick action cards ───────────────────────────────────────────────────────

function QuickActionCard({
  icon: Icon,
  title,
  subtitle,
  buttonLabel,
  onClick,
  disabled = false,
}: {
  icon: React.ElementType
  title: string
  subtitle: string
  buttonLabel: string
  onClick: () => void
  disabled?: boolean
}) {
  return (
    <div
      className="rounded-lg p-4 flex flex-col gap-3 transition-all cursor-pointer group"
      style={{
        background: 'var(--color-surface)',
        border: '1px solid var(--color-border)',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = 'var(--color-primary)'
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = 'var(--color-border)'
      }}
    >
      <div
        className="w-9 h-9 rounded-lg flex items-center justify-center"
        style={{ background: 'var(--color-surface-raised)' }}
      >
        <Icon size={18} style={{ color: 'var(--color-primary)' }} />
      </div>
      <div>
        <p className="text-sm font-semibold text-text">{title}</p>
        <p className="text-xs text-text-muted mt-0.5 leading-snug">{subtitle}</p>
      </div>
      <button
        onClick={onClick}
        disabled={disabled}
        className="mt-auto text-xs font-medium px-3 py-1.5 rounded transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        style={{ background: 'var(--color-surface-raised)', color: 'var(--color-text-muted)' }}
        onMouseEnter={(e) => {
          if (!disabled) {
            e.currentTarget.style.background = 'var(--color-primary)'
            e.currentTarget.style.color = '#fff'
          }
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.background = 'var(--color-surface-raised)'
          e.currentTarget.style.color = 'var(--color-text-muted)'
        }}
      >
        {buttonLabel}
      </button>
    </div>
  )
}

// ─── Metrics summary table ────────────────────────────────────────────────────

const PILLAR_COLORS: Record<string, string> = {
  E: '#10B981',
  S: '#38BDF8',
  G: '#A78BFA',
}

function PillarChip({ pillar }: { pillar: string | null | undefined }) {
  if (!pillar) return <span className="text-text-subtle">—</span>
  const color = PILLAR_COLORS[pillar] ?? '#6B7280'
  return (
    <span
      className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold"
      style={{ background: `${color}20`, color }}
    >
      {pillar}
    </span>
  )
}

function ConfidenceCell({ value }: { value: number }) {
  const pct = Math.round(value * 100)
  const color = pct >= 80 ? '#10B981' : pct >= 50 ? '#F59E0B' : '#EF4444'
  return (
    <span
      className="text-xs font-medium tabular-nums"
      style={{ color, fontFamily: 'var(--font-mono)' }}
    >
      {pct}%
    </span>
  )
}

function MetricsSummaryTable({
  metrics,
  documentName,
  documentId,
}: {
  metrics: MetricDTO[]
  documentName: string
  documentId: string
}) {
  const preview = metrics.slice(0, 8)

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <div>
          <p className="text-sm font-semibold text-text">Latest Extraction</p>
          <p className="text-xs text-text-muted mt-0.5">{documentName}</p>
        </div>
        <Link
          to={`/results/${documentId}`}
          className="text-xs text-primary hover:underline flex items-center gap-1"
        >
          View all metrics <ArrowRight size={12} />
        </Link>
      </div>
      <div
        className="rounded-lg overflow-hidden"
        style={{ border: '1px solid var(--color-border)' }}
      >
        <table className="w-full text-sm">
          <thead>
            <tr style={{ background: 'var(--color-surface)', borderBottom: '1px solid var(--color-border)' }}>
              {['GRI Code', 'Indicator', 'Value', 'Unit', 'Pillar', 'Confidence', 'Status'].map(
                (h) => (
                  <th
                    key={h}
                    className="px-3 py-2.5 text-left text-xs font-semibold text-text-muted whitespace-nowrap"
                  >
                    {h}
                  </th>
                ),
              )}
            </tr>
          </thead>
          <tbody>
            {preview.map((m, i) => (
              <tr
                key={m.id}
                style={{
                  background: i % 2 === 0 ? 'var(--color-surface)' : 'var(--color-bg)',
                  borderBottom: '1px solid var(--color-border)',
                }}
              >
                <td
                  className="px-3 py-2.5 text-xs font-medium whitespace-nowrap"
                  style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-primary)' }}
                >
                  {m.gri_code}
                </td>
                <td className="px-3 py-2.5 text-xs text-text max-w-[200px] truncate">
                  {m.label}
                </td>
                <td
                  className="px-3 py-2.5 text-xs text-text tabular-nums"
                  style={{ fontFamily: 'var(--font-mono)' }}
                >
                  {m.original_value ?? (m.value != null ? String(m.value) : '—')}
                </td>
                <td className="px-3 py-2.5 text-xs text-text-muted">{m.unit ?? '—'}</td>
                <td className="px-3 py-2.5">
                  <PillarChip pillar={m.pillar} />
                </td>
                <td className="px-3 py-2.5">
                  <ConfidenceCell value={m.confidence} />
                </td>
                <td className="px-3 py-2.5">
                  <StatusPill status={m.status as StatusValue} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {metrics.length === 0 && (
          <div className="px-4 py-6 text-center text-sm text-text-subtle">
            No metrics extracted yet.
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Empty state ──────────────────────────────────────────────────────────────

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-center">
      <div
        className="w-14 h-14 rounded-full flex items-center justify-center mb-5"
        style={{ background: 'var(--color-surface-raised)' }}
      >
        <FileText size={24} style={{ color: 'var(--color-primary)' }} />
      </div>
      <p className="text-base font-semibold text-text mb-2">No documents yet</p>
      <p className="text-sm text-text-muted mb-6 max-w-sm">
        Upload your first ESG report to get started. The pipeline will extract, score, and
        structure your data automatically.
      </p>
      <Link
        to="/upload"
        className="inline-flex items-center gap-2 px-5 py-2.5 text-sm font-semibold rounded transition-colors"
        style={{ background: 'var(--color-primary)', color: '#fff' }}
        onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--color-primary-hover)')}
        onMouseLeave={(e) => (e.currentTarget.style.background = 'var(--color-primary)')}
      >
        <Upload size={15} />
        Upload Document
      </Link>
    </div>
  )
}

// ─── Dashboard ────────────────────────────────────────────────────────────────

export default function Dashboard() {
  const navigate = useNavigate()
  const userId = useAuthStore((s) => s.userId)
  const queryClient = useQueryClient()

  const generateMutation = useMutation({
    mutationFn: (documentId: string) => generateReport({ document_id: documentId }),
    onSuccess: (job, documentId) => {
      queryClient.invalidateQueries({ queryKey: ['reports'] })
      navigate(`/report/${job.report_id}?doc=${documentId}`)
    },
  })

  const { data: documents, isLoading: docsLoading } = useQuery({
    queryKey: ['documents'],
    queryFn: listDocuments,
  })

  const latestDoc = documents?.[documents.length - 1]

  const { data: metrics = [], isLoading: metricsLoading } = useQuery({
    queryKey: ['metrics', latestDoc?.document_id],
    queryFn: () => getMetrics(latestDoc!.document_id),
    enabled: !!latestDoc?.document_id,
  })

  const { data: reports = [] } = useQuery({
    queryKey: ['reports'],
    queryFn: listReports,
  })

  const latestReport = reports[reports.length - 1]
  const hasApprovedMetrics = metrics.some((m) => m.status === 'approved')

  const loading = docsLoading || metricsLoading
  const hasDocuments = (documents?.length ?? 0) > 0

  const greeting = (() => {
    const h = new Date().getHours()
    if (h < 12) return 'Good morning'
    if (h < 18) return 'Good afternoon'
    return 'Good evening'
  })()

  return (
    <div className="p-6 max-w-[1400px] mx-auto">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-[28px] font-semibold text-text leading-tight">
          {greeting}{userId ? '' : ''}
        </h1>
        <p className="text-sm text-text-muted mt-1">
          {hasDocuments
            ? `Here's your ESG reporting status${latestDoc ? ` — ${latestDoc.filename}` : ''}`
            : 'Upload a document to begin your ESG reporting workflow.'}
        </p>
      </div>

      {loading && (
        <div className="flex flex-col gap-6">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-64" />
            ))}
          </div>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-40" />
            ))}
          </div>
          <Skeleton className="h-72" />
        </div>
      )}

      {!loading && !hasDocuments && <EmptyState />}

      {!loading && hasDocuments && (
        <div className="flex flex-col gap-6">
          {/* Row 1 — Score overview */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <ScoreCard metrics={metrics} />
            <CoverageCard metrics={metrics} />
            <ActivityFeed documents={documents ?? []} metrics={metrics} />
          </div>

          {/* Row 2 — Quick actions */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <QuickActionCard
              icon={Upload}
              title="Upload Document"
              subtitle="Add an Arabic or English ESG report to the pipeline."
              buttonLabel="Upload"
              onClick={() => navigate('/upload')}
            />
            <QuickActionCard
              icon={BarChart2}
              title="Review Metrics"
              subtitle="Approve, reject, or edit extracted values."
              buttonLabel="Review"
              onClick={() =>
                navigate(latestDoc ? `/results/${latestDoc.document_id}` : '/results')
              }
              disabled={!latestDoc}
            />
            <QuickActionCard
              icon={FileText}
              title="Generate Report"
              subtitle="Create a GRI/FRA-compliant PDF disclosure."
              buttonLabel={
                generateMutation.isPending
                  ? 'Generating…'
                  : hasApprovedMetrics
                  ? 'Generate'
                  : 'Approve metrics first'
              }
              onClick={() => {
                if (latestDoc?.document_id) generateMutation.mutate(latestDoc.document_id)
              }}
              disabled={!hasApprovedMetrics || generateMutation.isPending}
            />
            <QuickActionCard
              icon={FileText}
              title="View Last Report"
              subtitle="Open your most recently generated disclosure PDF."
              buttonLabel="Open"
              onClick={() => {
                const docSuffix = latestDoc ? `?doc=${latestDoc.document_id}` : ''
                navigate(latestReport ? `/report/${latestReport.id}${docSuffix}` : '/report')
              }}
              disabled={!latestReport}
            />
          </div>

          {/* Row 3 — Metrics table */}
          {latestDoc && (
            <MetricsSummaryTable
              metrics={metrics}
              documentName={latestDoc.filename}
              documentId={latestDoc.document_id}
            />
          )}
        </div>
      )}
    </div>
  )
}
