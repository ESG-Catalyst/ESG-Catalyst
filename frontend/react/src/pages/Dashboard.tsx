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
  TrendingUp,
  Activity,
} from 'lucide-react'
import { motion } from 'framer-motion'
import ScoreGauge from '@/components/ui/ScoreGauge'
import FrameworkCoverageBar from '@/components/ui/FrameworkCoverageBar'
import StatusPill, { type StatusValue } from '@/components/ui/StatusPill'
import { listDocuments } from '@/api/documents'
import { getMetrics, type MetricDTO } from '@/api/metrics'
import { listReports, generateReport } from '@/api/reports'
import { useAuthStore, emailHandle } from '@/store/auth'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'

// ─── Skeleton ─────────────────────────────────────────────────────────────────

function Skeleton({ className = '' }: { className?: string }) {
  return (
    <div
      className={cn('rounded-lg animate-pulse bg-surface-raised', className)}
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
      className={cn('rounded-xl p-5 bg-surface border border-border', className)}
      style={style}
    >
      {children}
    </div>
  )
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-[10px] font-bold uppercase tracking-widest text-text-muted mb-4">
      {children}
    </p>
  )
}

// ─── Tier helpers ─────────────────────────────────────────────────────────────

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

// ─── Stat chip ────────────────────────────────────────────────────────────────

function StatChip({
  label,
  value,
  color,
}: {
  label: string
  value: number | string
  color: string
}) {
  return (
    <div className="flex flex-col items-center gap-0.5 px-4 py-3 rounded-lg bg-surface-raised">
      <span className="text-xl font-bold tabular-nums" style={{ color, fontFamily: 'var(--font-mono)' }}>
        {value}
      </span>
      <span className="text-[10px] text-text-muted uppercase tracking-wide">{label}</span>
    </div>
  )
}

// ─── Score overview card ──────────────────────────────────────────────────────

function ScoreCard({ metrics }: { metrics: MetricDTO[] }) {
  const { t } = useTranslation()
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
  const tierColor = TIER_COLOR(tier)

  const approved = metrics.filter((m) => m.status === 'approved').length
  const extracted = metrics.filter((m) => m.status === 'extracted').length
  const missing = metrics.filter((m) => m.status === 'missing').length

  return (
    <Card className="flex flex-col gap-4">
      <SectionTitle>{t('dashboard.esg_score_overview')}</SectionTitle>

      <div className="flex justify-center">
        <ScoreGauge scores={scores} overall={overall} size="md" />
      </div>

      {/* Tier badge */}
      <div className="flex justify-center">
        <span
          className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold border"
          style={{
            background: `${tierColor}18`,
            color: tierColor,
            borderColor: `${tierColor}35`,
          }}
        >
          <TrendingUp size={11} aria-hidden="true" />
          {tier}
        </span>
      </div>

      {/* Stat chips */}
      <div className="grid grid-cols-3 gap-2 mt-1">
        <StatChip label={t('dashboard.stat_approved')} value={approved} color="#10B981" />
        <StatChip label={t('dashboard.stat_extracted')} value={extracted} color="#38BDF8" />
        <StatChip label={t('dashboard.stat_missing')} value={missing} color="#F59E0B" />
      </div>
    </Card>
  )
}

// ─── Framework coverage card ──────────────────────────────────────────────────

function CoverageCard({ metrics }: { metrics: MetricDTO[] }) {
  const { t } = useTranslation()
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

  const totalDisclosed = metrics.filter(
    (m) => m.status === 'extracted' || m.status === 'approved',
  ).length

  return (
    <Card className="flex flex-col gap-4">
      <SectionTitle>{t('dashboard.framework_coverage')}</SectionTitle>
      <div className="flex flex-col gap-5">
        <FrameworkCoverageBar framework="GRI" covered={disclosed('GRI')} total={GRI_TOTAL} />
        <FrameworkCoverageBar framework="FRA" covered={disclosed('FRA')} total={FRA_TOTAL} />
        <FrameworkCoverageBar framework="SASB" covered={disclosed('SASB')} total={SASB_TOTAL} />
      </div>
      <div className="flex items-center gap-2 pt-1 border-t border-border-subtle">
        <Activity size={12} className="text-text-subtle" aria-hidden="true" />
        <p className="text-xs text-text-subtle">
          {t('dashboard.indicators_disclosed', { count: totalDisclosed })}
        </p>
      </div>
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

function timeAgo(dateStr: string, t: (k: string, o?: Record<string, unknown>) => string): string {
  const diff = (Date.now() - new Date(dateStr).getTime()) / 1000
  if (diff < 60) return t('time.just_now')
  if (diff < 3600) return t('time.minutes_ago', { n: Math.floor(diff / 60) })
  if (diff < 86400) return t('time.hours_ago', { n: Math.floor(diff / 3600) })
  return t('time.days_ago', { n: Math.floor(diff / 86400) })
}

function ActivityFeed({
  documents,
  metrics,
}: {
  documents: { filename: string; status: string; uploaded_at?: string }[]
  metrics: MetricDTO[]
}) {
  const { t } = useTranslation()
  const items: ActivityItem[] = []

  documents.slice(0, 2).forEach((doc) => {
    if (doc.uploaded_at) {
      items.push({
        icon: Upload,
        color: '#38BDF8',
        text: t('dashboard.activity_uploaded', { filename: doc.filename }),
        time: timeAgo(doc.uploaded_at, t),
      })
    }
    if (doc.status === 'complete' || doc.status === 'extracted') {
      items.push({
        icon: BarChart2,
        color: '#0D9488',
        text: t('dashboard.activity_pipeline_complete', { filename: doc.filename }),
        time: doc.uploaded_at ? timeAgo(doc.uploaded_at, t) : '—',
      })
    }
  })

  const approved = metrics.filter((m) => m.status === 'approved').length
  if (approved > 0) {
    items.push({
      icon: CheckCircle2,
      color: '#10B981',
      text: t('dashboard.activity_metrics_approved', { count: approved }),
      time: t('time.recently'),
    })
  }

  const missing = metrics.filter((m) => m.status === 'missing').length
  if (missing > 0) {
    items.push({
      icon: AlertCircle,
      color: '#F59E0B',
      text: t('dashboard.activity_indicators_missing', { count: missing }),
      time: t('dashboard.activity_pending'),
    })
  }

  const feed = items.slice(0, 5)

  return (
    <Card className="flex flex-col gap-4">
      <SectionTitle>{t('dashboard.recent_activity')}</SectionTitle>

      {feed.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-6 gap-2 text-center">
          <Activity size={20} className="text-text-subtle opacity-50" />
          <p className="text-sm text-text-subtle">{t('dashboard.no_activity')}</p>
        </div>
      ) : (
        <ul className="flex flex-col gap-3" role="list">
          {feed.map((item, i) => (
            <li key={i} className="flex items-start gap-3">
              <div
                className="w-6 h-6 rounded-lg shrink-0 flex items-center justify-center mt-0.5"
                style={{ background: `${item.color}18` }}
              >
                <item.icon size={12} style={{ color: item.color }} aria-hidden="true" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm text-text leading-snug">{item.text}</p>
              </div>
              <span className="text-xs text-text-subtle shrink-0 flex items-center gap-1 mt-0.5">
                <Clock size={10} aria-hidden="true" />
                {item.time}
              </span>
            </li>
          ))}
        </ul>
      )}

      <Link
        to="/results"
        className="flex items-center gap-1 text-xs text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary rounded mt-auto pt-1 border-t border-border-subtle"
      >
        {t('dashboard.view_all_activity')} <ArrowRight size={12} aria-hidden="true" />
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
  variant = 'default',
}: {
  icon: React.ElementType
  title: string
  subtitle: string
  buttonLabel: string
  onClick: () => void
  disabled?: boolean
  variant?: 'default' | 'primary'
}) {
  return (
    <motion.div
      whileHover={{ y: -2 }}
      transition={{ duration: 0.15 }}
      className="rounded-xl p-4 flex flex-col gap-3 border border-border bg-surface cursor-pointer"
      style={{ transition: 'border-color 0.15s' }}
      onMouseEnter={(e) => {
        ;(e.currentTarget as HTMLDivElement).style.borderColor = 'var(--color-primary)'
      }}
      onMouseLeave={(e) => {
        ;(e.currentTarget as HTMLDivElement).style.borderColor = 'var(--color-border)'
      }}
    >
      {/* Icon */}
      <div
        className="w-9 h-9 rounded-lg flex items-center justify-center"
        style={{
          background: variant === 'primary' ? 'var(--color-primary)' : 'var(--color-surface-raised)',
        }}
      >
        <Icon
          size={18}
          style={{ color: variant === 'primary' ? '#fff' : 'var(--color-primary)' }}
          aria-hidden="true"
        />
      </div>

      <div className="flex-1">
        <p className="text-sm font-semibold text-text">{title}</p>
        <p className="text-xs text-text-muted mt-0.5 leading-snug">{subtitle}</p>
      </div>

      <button
        onClick={onClick}
        disabled={disabled}
        className="mt-auto text-xs font-semibold px-3 py-1.5 rounded-lg transition-all disabled:opacity-40 disabled:cursor-not-allowed bg-primary hover:bg-primary-hover text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
      >
        {buttonLabel}
      </button>
    </motion.div>
  )
}

// ─── Pillar chip + Confidence cell ────────────────────────────────────────────

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
      style={{ background: `${color}18`, color }}
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

// ─── Metrics summary table ────────────────────────────────────────────────────

function MetricsSummaryTable({
  metrics,
  documentName,
  documentId,
}: {
  metrics: MetricDTO[]
  documentName: string
  documentId: string
}) {
  const { t } = useTranslation()
  const preview = metrics.slice(0, 8)

  return (
    <div className="rounded-xl border border-border overflow-hidden">
      {/* Table header row */}
      <div className="flex items-center justify-between px-5 py-3.5 bg-surface border-b border-border">
        <div>
          <p className="text-sm font-semibold text-text">{t('dashboard.latest_extraction')}</p>
          <p className="text-xs text-text-muted mt-0.5 truncate max-w-[280px]">{documentName}</p>
        </div>
        <Link
          to={`/results/${documentId}`}
          className="text-xs text-primary hover:underline flex items-center gap-1 shrink-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary rounded"
        >
          {t('dashboard.view_all_metrics')} <ArrowRight size={12} aria-hidden="true" />
        </Link>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-surface-raised border-b border-border">
              {[
                t('dashboard.table_headers.gri_code'),
                t('dashboard.table_headers.indicator'),
                t('dashboard.table_headers.value'),
                t('dashboard.table_headers.unit'),
                t('dashboard.table_headers.pillar'),
                t('dashboard.table_headers.confidence'),
                t('dashboard.table_headers.status'),
              ].map(
                (h) => (
                  <th
                    key={h}
                    scope="col"
                    className="px-4 py-2.5 text-start text-xs font-semibold text-text-muted whitespace-nowrap"
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
                className={cn(
                  'border-b border-border transition-colors',
                  i % 2 === 0 ? 'bg-surface' : 'bg-bg',
                )}
              >
                <td className="px-4 py-2.5 text-xs font-medium whitespace-nowrap text-primary"
                  style={{ fontFamily: 'var(--font-mono)' }}>
                  {m.gri_code}
                </td>
                <td className="px-4 py-2.5 text-xs text-text max-w-[200px] truncate">
                  {m.label}
                </td>
                <td className="px-4 py-2.5 text-xs text-text tabular-nums"
                  style={{ fontFamily: 'var(--font-mono)' }}>
                  {m.original_value ?? (m.value != null ? String(m.value) : '—')}
                </td>
                <td className="px-4 py-2.5 text-xs text-text-muted">{m.unit ?? '—'}</td>
                <td className="px-4 py-2.5">
                  <PillarChip pillar={m.pillar} />
                </td>
                <td className="px-4 py-2.5">
                  <ConfidenceCell value={m.confidence} />
                </td>
                <td className="px-4 py-2.5">
                  <StatusPill status={m.status as StatusValue} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {metrics.length === 0 && (
          <div className="px-4 py-8 text-center text-sm text-text-subtle">
            {t('dashboard.no_metrics_yet')}
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Empty state ──────────────────────────────────────────────────────────────

function EmptyState() {
  const { t } = useTranslation()
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="flex flex-col items-center justify-center py-20 text-center"
    >
      <div className="w-16 h-16 rounded-2xl bg-surface-raised flex items-center justify-center mb-5 border border-border">
        <FileText size={28} style={{ color: 'var(--color-primary)' }} aria-hidden="true" />
      </div>
      <p className="text-base font-semibold text-text mb-2">{t('dashboard.no_documents')}</p>
      <p className="text-sm text-text-muted mb-6 max-w-sm leading-relaxed">
        {t('dashboard.no_documents_hint')}
      </p>
      <Link
        to="/upload"
        className="inline-flex items-center gap-2 px-5 py-2.5 text-sm font-semibold rounded-lg transition-all bg-primary hover:bg-primary-hover text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
      >
        <Upload size={15} aria-hidden="true" />
        {t('dashboard.upload_document_cta')}
      </Link>
    </motion.div>
  )
}

// ─── Loading skeleton layout ──────────────────────────────────────────────────

function LoadingSkeleton() {
  return (
    <div className="flex flex-col gap-6" aria-label="Loading dashboard…" aria-busy="true">
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
  )
}

// ─── Dashboard ────────────────────────────────────────────────────────────────

export default function Dashboard() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const email = useAuthStore((s) => s.email)
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
    if (h < 12) return t('dashboard.greeting_morning')
    if (h < 18) return t('dashboard.greeting_afternoon')
    return t('dashboard.greeting_evening')
  })()

  const handle = emailHandle(email)

  return (
    <div className="p-6 max-w-[1400px] mx-auto">
      {/* Page header */}
      <motion.div
        initial={{ opacity: 0, y: -6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
        className="mb-8"
      >
        <h1 className="text-2xl font-semibold text-text leading-tight">
          {greeting}
          {handle && handle !== 'User' ? `, ${handle}` : ''}
        </h1>
        <p className="text-sm text-text-muted mt-1">
          {hasDocuments
            ? t('dashboard.status_with_doc', { filename: latestDoc?.filename ?? '' })
            : t('dashboard.status_empty')}
        </p>
      </motion.div>

      {loading && <LoadingSkeleton />}

      {!loading && !hasDocuments && <EmptyState />}

      {!loading && hasDocuments && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.25 }}
          className="flex flex-col gap-6"
        >
          {/* Row 1 — Score, coverage, activity */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <ScoreCard metrics={metrics} />
            <CoverageCard metrics={metrics} />
            <ActivityFeed documents={documents ?? []} metrics={metrics} />
          </div>

          {/* Row 2 — Quick actions */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <QuickActionCard
              icon={Upload}
              title={t('dashboard.action_upload_title')}
              subtitle={t('dashboard.action_upload_subtitle')}
              buttonLabel={t('dashboard.action_upload_button')}
              onClick={() => navigate('/upload')}
              variant="primary"
            />
            <QuickActionCard
              icon={BarChart2}
              title={t('dashboard.action_review_title')}
              subtitle={t('dashboard.action_review_subtitle')}
              buttonLabel={t('dashboard.action_review_button')}
              onClick={() =>
                navigate(latestDoc ? `/results/${latestDoc.document_id}` : '/results')
              }
              disabled={!latestDoc}
            />
            <QuickActionCard
              icon={FileText}
              title={t('dashboard.action_generate_title')}
              subtitle={t('dashboard.action_generate_subtitle')}
              buttonLabel={
                generateMutation.isPending
                  ? t('dashboard.action_generate_button_generating')
                  : hasApprovedMetrics
                  ? t('dashboard.action_generate_button')
                  : t('dashboard.action_generate_button_disabled')
              }
              onClick={() => {
                if (latestDoc?.document_id) generateMutation.mutate(latestDoc.document_id)
              }}
              disabled={!hasApprovedMetrics || generateMutation.isPending}
            />
            <QuickActionCard
              icon={FileText}
              title={t('dashboard.action_view_report_title')}
              subtitle={t('dashboard.action_view_report_subtitle')}
              buttonLabel={t('dashboard.action_view_report_button')}
              onClick={() => {
                const docSuffix = latestDoc ? `?doc=${latestDoc.document_id}` : ''
                navigate(latestReport ? `/report/${latestReport.id}${docSuffix}` : '/report')
              }}
              disabled={!latestReport}
            />
          </div>

          {/* Row 3 — Metrics summary table */}
          {latestDoc && (
            <MetricsSummaryTable
              metrics={metrics}
              documentName={latestDoc.filename}
              documentId={latestDoc.document_id}
            />
          )}
        </motion.div>
      )}
    </div>
  )
}
