import { useState, type FormEvent } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import {
  Building2,
  Plus,
  X,
  ChevronDown,
  Download,
  Clock,
  CheckCircle2,
  FileText,
  AlertCircle,
  BarChart2,
  Users,
} from 'lucide-react'
import ScoreGauge from '@/components/ui/ScoreGauge'
import { useConsultantStore } from '@/store/consultant'
import { useAuthStore } from '@/store/auth'

// ─── Types ────────────────────────────────────────────────────────────────────

type InstitutionType = 'Commercial Bank' | 'NBFI' | 'Insurance'
type ReportStatus = 'DRAFT' | 'Pending review' | 'Report locked'

interface ClientInstitution {
  id: string
  name: string
  type: InstitutionType
  scores: { E: number; S: number; G: number; overall: number }
  lastActivity: string
  reportStatus: ReportStatus
  latestReportId: string | null
  griCoverage: number
  fraCoverage: number
  missingIndicators: number
  tier: string
}

interface ActivityItem {
  institutionId: string
  institutionName: string
  action: string
  time: string
  icon: React.ElementType
  iconColor: string
}

// ─── Mock data ────────────────────────────────────────────────────────────────

const MOCK_CLIENTS: ClientInstitution[] = [
  {
    id: 'c1',
    name: 'ADCB Egypt',
    type: 'Commercial Bank',
    scores: { E: 68, S: 72, G: 81, overall: 74 },
    lastActivity: '3 days ago',
    reportStatus: 'DRAFT',
    latestReportId: 'r-adcb-001',
    griCoverage: 62,
    fraCoverage: 100,
    missingIndicators: 9,
    tier: 'Established',
  },
  {
    id: 'c2',
    name: 'Beltone Financial',
    type: 'NBFI',
    scores: { E: 45, S: 61, G: 58, overall: 55 },
    lastActivity: '1 day ago',
    reportStatus: 'Pending review',
    latestReportId: 'r-beltone-002',
    griCoverage: 38,
    fraCoverage: 100,
    missingIndicators: 17,
    tier: 'Established',
  },
  {
    id: 'c3',
    name: 'ADIB Egypt',
    type: 'Commercial Bank',
    scores: { E: 28, S: 34, G: 41, overall: 34 },
    lastActivity: '5 days ago',
    reportStatus: 'DRAFT',
    latestReportId: null,
    griCoverage: 21,
    fraCoverage: 0,
    missingIndicators: 31,
    tier: 'Laggard',
  },
  {
    id: 'c4',
    name: 'EFG Hermes',
    type: 'NBFI',
    scores: { E: 83, S: 79, G: 88, overall: 83 },
    lastActivity: '12 hours ago',
    reportStatus: 'Report locked',
    latestReportId: 'r-efg-004',
    griCoverage: 79,
    fraCoverage: 100,
    missingIndicators: 5,
    tier: 'Leading',
  },
]

const MOCK_ACTIVITY: ActivityItem[] = [
  {
    institutionId: 'c4',
    institutionName: 'EFG Hermes',
    action: 'Report approved and locked',
    time: '12h ago',
    icon: CheckCircle2,
    iconColor: '#10B981',
  },
  {
    institutionId: 'c2',
    institutionName: 'Beltone Financial',
    action: 'Pipeline completed — 8 metrics extracted',
    time: '1d ago',
    icon: BarChart2,
    iconColor: '#0D9488',
  },
  {
    institutionId: 'c2',
    institutionName: 'Beltone Financial',
    action: 'ESG report uploaded for processing',
    time: '1d ago',
    icon: FileText,
    iconColor: '#38BDF8',
  },
  {
    institutionId: 'c1',
    institutionName: 'ADCB Egypt',
    action: '3 metrics approved by reviewer',
    time: '3d ago',
    icon: CheckCircle2,
    iconColor: '#10B981',
  },
  {
    institutionId: 'c3',
    institutionName: 'ADIB Egypt',
    action: '31 indicators still missing disclosure',
    time: '5d ago',
    icon: AlertCircle,
    iconColor: '#F59E0B',
  },
]

// ─── Helpers ──────────────────────────────────────────────────────────────────

function TIER_COLOR(tier: string): string {
  if (tier === 'Leading') return '#10B981'
  if (tier === 'Established') return '#0D9488'
  if (tier === 'Developing') return '#F59E0B'
  return '#EF4444'
}

function TYPE_BADGE_STYLE(type: InstitutionType): React.CSSProperties {
  const map: Record<InstitutionType, { bg: string; color: string }> = {
    'Commercial Bank': { bg: '#38BDF820', color: '#38BDF8' },
    NBFI: { bg: '#A78BFA20', color: '#A78BFA' },
    Insurance: { bg: '#F59E0B20', color: '#F59E0B' },
  }
  const s = map[type]
  return { background: s.bg, color: s.color, border: `1px solid ${s.color}40` }
}

function REPORT_STATUS_STYLE(status: ReportStatus): React.CSSProperties {
  if (status === 'Report locked') return { background: '#A78BFA20', color: '#A78BFA', border: '1px solid #A78BFA40' }
  if (status === 'Pending review') return { background: '#F59E0B20', color: '#F59E0B', border: '1px solid #F59E0B40' }
  return { background: '#6B728020', color: '#9CA3AF', border: '1px solid #6B728040' }
}

// ─── Shared Card ──────────────────────────────────────────────────────────────

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
      className={`rounded-lg ${className}`}
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

// ─── Add Client Modal ─────────────────────────────────────────────────────────

function AddClientModal({ onClose }: { onClose: () => void }) {
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [type, setType] = useState<InstitutionType>('Commercial Bank')
  const [submitted, setSubmitted] = useState(false)

  function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    if (!name.trim() || !email.trim()) return
    setSubmitted(true)
    setTimeout(onClose, 1200)
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(2px)' }}
      onClick={onClose}
    >
      <div
        className="rounded-xl p-6 w-full max-w-md mx-4 shadow-2xl"
        style={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)' }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-base font-semibold text-text">Add Client Institution</h2>
          <button
            onClick={onClose}
            className="text-text-muted hover:text-text transition-colors rounded p-1"
          >
            <X size={16} />
          </button>
        </div>

        {submitted ? (
          <div className="py-6 flex flex-col items-center gap-3 text-center">
            <CheckCircle2 size={32} style={{ color: '#10B981' }} />
            <p className="text-sm font-medium text-text">Invitation sent successfully</p>
            <p className="text-xs text-text-muted">
              {name} will receive an onboarding email at {email}.
            </p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-text-muted">Institution name</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Cairo International Bank"
                className="rounded-lg px-3 py-2 text-sm outline-none"
                style={{
                  background: 'var(--color-surface-raised)',
                  border: '1px solid var(--color-border)',
                  color: 'var(--color-text)',
                }}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-text-muted">Institution type</label>
              <select
                value={type}
                onChange={(e) => setType(e.target.value as InstitutionType)}
                className="rounded-lg px-3 py-2 text-sm outline-none appearance-none"
                style={{
                  background: 'var(--color-surface-raised)',
                  border: '1px solid var(--color-border)',
                  color: 'var(--color-text)',
                }}
              >
                <option>Commercial Bank</option>
                <option>NBFI</option>
                <option>Insurance</option>
              </select>
            </div>
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-text-muted">Contact email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="sustainability@bank.eg"
                className="rounded-lg px-3 py-2 text-sm outline-none"
                style={{
                  background: 'var(--color-surface-raised)',
                  border: '1px solid var(--color-border)',
                  color: 'var(--color-text)',
                }}
              />
            </div>
            <div className="flex gap-3 mt-1">
              <button
                type="button"
                onClick={onClose}
                className="flex-1 py-2 rounded-lg text-sm font-medium transition-colors"
                style={{ background: 'var(--color-surface-raised)', color: 'var(--color-text-muted)' }}
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={!name.trim() || !email.trim()}
                className="flex-1 py-2 rounded-lg text-sm font-semibold transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                style={{ background: 'var(--color-primary)', color: '#fff' }}
              >
                Send Invitation
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}

// ─── Pillar bars ──────────────────────────────────────────────────────────────

function PillarBar({ label, score, color }: { label: string; score: number; color: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs font-medium w-3" style={{ color }}>{label}</span>
      <div
        className="flex-1 rounded-full overflow-hidden h-1.5"
        style={{ background: 'var(--color-border-subtle)' }}
      >
        <div
          className="h-full rounded-full transition-all"
          style={{ width: `${score}%`, background: color }}
        />
      </div>
      <span
        className="text-xs tabular-nums w-7 text-right"
        style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-mono)' }}
      >
        {score}
      </span>
    </div>
  )
}

// ─── Client Card ──────────────────────────────────────────────────────────────

function ClientCard({ client }: { client: ClientInstitution }) {
  const navigate = useNavigate()
  const setActiveClient = useConsultantStore((s) => s.setActiveClient)

  function openDashboard() {
    setActiveClient({
      companyId: client.id,
      companyName: client.name,
      institutionType: client.type,
    })
    navigate('/dashboard')
  }

  return (
    <Card className="p-5 flex flex-col gap-4 hover:border-primary transition-colors" style={{ borderColor: undefined }}>
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <h3 className="text-base font-semibold text-text truncate">{client.name}</h3>
          <span
            className="inline-flex items-center mt-1 px-2 py-0.5 rounded-full text-xs font-medium"
            style={TYPE_BADGE_STYLE(client.type)}
          >
            {client.type}
          </span>
        </div>
        <div
          className="shrink-0 w-16 h-16 flex items-center justify-center rounded-lg"
          style={{ background: 'var(--color-surface-raised)' }}
        >
          <Building2 size={22} style={{ color: 'var(--color-primary)' }} />
        </div>
      </div>

      {/* Score gauge + pillar bars */}
      <div className="flex items-center gap-4">
        <div className="shrink-0">
          <ScoreGauge scores={client.scores} overall={client.scores.overall} size="sm" />
        </div>
        <div className="flex-1 flex flex-col gap-1.5">
          <PillarBar label="E" score={client.scores.E} color="#10B981" />
          <PillarBar label="S" score={client.scores.S} color="#38BDF8" />
          <PillarBar label="G" score={client.scores.G} color="#A78BFA" />
        </div>
      </div>

      {/* Meta row */}
      <div className="flex items-center justify-between text-xs text-text-muted">
        <span className="flex items-center gap-1">
          <Clock size={11} />
          Updated {client.lastActivity}
        </span>
        <span
          className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium"
          style={REPORT_STATUS_STYLE(client.reportStatus)}
        >
          {client.reportStatus}
        </span>
      </div>

      {/* Tier badge */}
      <div className="flex items-center gap-2">
        <span
          className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold"
          style={{
            background: `${TIER_COLOR(client.tier)}20`,
            color: TIER_COLOR(client.tier),
            border: `1px solid ${TIER_COLOR(client.tier)}40`,
          }}
        >
          {client.tier}
        </span>
        <span className="text-xs text-text-subtle">
          {client.griCoverage}% GRI · {client.missingIndicators} missing
        </span>
      </div>

      {/* Actions */}
      <div className="flex gap-2 mt-1">
        <button
          onClick={openDashboard}
          className="flex-1 py-1.5 rounded-lg text-xs font-semibold transition-all"
          style={{ background: 'var(--color-primary)', color: '#fff' }}
          onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--color-primary-hover)')}
          onMouseLeave={(e) => (e.currentTarget.style.background = 'var(--color-primary)')}
        >
          Open Dashboard
        </button>
        {client.latestReportId ? (
          <Link
            to={`/report/${client.latestReportId}`}
            className="flex-1 py-1.5 rounded-lg text-xs font-semibold text-center transition-all"
            style={{ background: 'var(--color-surface-raised)', color: 'var(--color-text-muted)' }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = 'var(--color-border)'
              e.currentTarget.style.color = 'var(--color-text)'
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = 'var(--color-surface-raised)'
              e.currentTarget.style.color = 'var(--color-text-muted)'
            }}
          >
            View Report
          </Link>
        ) : (
          <button
            disabled
            className="flex-1 py-1.5 rounded-lg text-xs font-semibold opacity-40 cursor-not-allowed"
            style={{ background: 'var(--color-surface-raised)', color: 'var(--color-text-muted)' }}
          >
            No Report Yet
          </button>
        )}
      </div>
    </Card>
  )
}

// ─── Comparison panel ─────────────────────────────────────────────────────────

const COMPARE_ROWS = [
  { key: 'overall', label: 'Overall Score' },
  { key: 'E', label: 'E Score' },
  { key: 'S', label: 'S Score' },
  { key: 'G', label: 'G Score' },
  { key: 'griCoverage', label: 'GRI Coverage %' },
  { key: 'fraCoverage', label: 'FRA Coverage %' },
  { key: 'missingIndicators', label: 'Missing Indicators', lowerIsBetter: true },
  { key: 'tier', label: 'Tier', isText: true },
] as const

type RowKey = (typeof COMPARE_ROWS)[number]['key']

function getCellValue(client: ClientInstitution, key: RowKey): number | string {
  if (key === 'overall') return client.scores.overall
  if (key === 'E') return client.scores.E
  if (key === 'S') return client.scores.S
  if (key === 'G') return client.scores.G
  if (key === 'griCoverage') return client.griCoverage
  if (key === 'fraCoverage') return client.fraCoverage
  if (key === 'missingIndicators') return client.missingIndicators
  return client.tier
}

function downloadComparisonCSV(clients: ClientInstitution[]) {
  const headers = ['Metric', ...clients.map((c) => c.name)]
  const rows = COMPARE_ROWS.map((row) => [
    row.label,
    ...clients.map((c) => String(getCellValue(c, row.key))),
  ])
  const csv = [headers, ...rows].map((r) => r.join(',')).join('\n')
  const blob = new Blob([csv], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'esg-comparison.csv'
  a.click()
  URL.revokeObjectURL(url)
}

function ComparisonPanel({ clients }: { clients: ClientInstitution[] }) {
  const [selected, setSelected] = useState<string[]>([])
  const [dropdownOpen, setDropdownOpen] = useState(false)

  const toggleClient = (id: string) => {
    setSelected((prev) =>
      prev.includes(id)
        ? prev.filter((x) => x !== id)
        : prev.length < 4
          ? [...prev, id]
          : prev,
    )
  }

  const comparedClients = clients.filter((c) => selected.includes(c.id))

  function getBestValue(key: RowKey, lowerIsBetter = false): number | string {
    const vals = comparedClients
      .map((c) => getCellValue(c, key))
      .filter((v) => typeof v === 'number') as number[]
    if (vals.length === 0) return ''
    return lowerIsBetter ? Math.min(...vals) : Math.max(...vals)
  }

  return (
    <Card className="p-5">
      <div className="flex items-center justify-between mb-5">
        <div>
          <h2 className="text-sm font-semibold text-text">Side-by-side comparison</h2>
          <p className="text-xs text-text-muted mt-0.5">Select 2–4 institutions to compare</p>
        </div>
        {comparedClients.length >= 2 && (
          <button
            onClick={() => downloadComparisonCSV(comparedClients)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors"
            style={{
              background: 'var(--color-surface-raised)',
              color: 'var(--color-text-muted)',
              border: '1px solid var(--color-border)',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.color = 'var(--color-text)'
              e.currentTarget.style.borderColor = 'var(--color-primary)'
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.color = 'var(--color-text-muted)'
              e.currentTarget.style.borderColor = 'var(--color-border)'
            }}
          >
            <Download size={12} />
            Export comparison
          </button>
        )}
      </div>

      {/* Multi-select dropdown */}
      <div className="relative mb-5">
        <button
          onClick={() => setDropdownOpen((v) => !v)}
          className="w-full flex items-center justify-between px-3 py-2.5 rounded-lg text-sm transition-colors"
          style={{
            background: 'var(--color-surface-raised)',
            border: '1px solid var(--color-border)',
            color: selected.length ? 'var(--color-text)' : 'var(--color-text-subtle)',
          }}
        >
          <span className="truncate">
            {selected.length === 0
              ? 'Choose institutions…'
              : clients
                  .filter((c) => selected.includes(c.id))
                  .map((c) => c.name)
                  .join(', ')}
          </span>
          <ChevronDown size={14} className={`shrink-0 ml-2 transition-transform ${dropdownOpen ? 'rotate-180' : ''}`} />
        </button>

        {dropdownOpen && (
          <div
            className="absolute z-20 top-full left-0 right-0 mt-1 rounded-lg py-1 shadow-lg overflow-hidden"
            style={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)' }}
          >
            {clients.map((c) => {
              const checked = selected.includes(c.id)
              const disabled = !checked && selected.length >= 4
              return (
                <button
                  key={c.id}
                  onClick={() => !disabled && toggleClient(c.id)}
                  disabled={disabled}
                  className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-left transition-colors disabled:opacity-40"
                  style={{ color: 'var(--color-text)' }}
                  onMouseEnter={(e) => {
                    if (!disabled) e.currentTarget.style.background = 'var(--color-surface-raised)'
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.background = 'transparent'
                  }}
                >
                  <div
                    className="w-4 h-4 rounded flex items-center justify-center shrink-0"
                    style={{
                      border: `2px solid ${checked ? 'var(--color-primary)' : 'var(--color-border)'}`,
                      background: checked ? 'var(--color-primary)' : 'transparent',
                    }}
                  >
                    {checked && (
                      <svg viewBox="0 0 8 8" width="8" height="8" fill="none">
                        <path d="M1.5 4L3 5.5L6.5 2" stroke="#fff" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                    )}
                  </div>
                  <span className="flex-1">{c.name}</span>
                  <span className="text-xs text-text-muted">{c.type}</span>
                </button>
              )
            })}
          </div>
        )}
      </div>

      {/* Comparison table */}
      {comparedClients.length < 2 ? (
        <div
          className="rounded-lg py-10 flex flex-col items-center gap-2 text-center"
          style={{ background: 'var(--color-surface-raised)' }}
        >
          <BarChart2 size={24} style={{ color: 'var(--color-text-subtle)' }} />
          <p className="text-sm text-text-muted">Select at least 2 institutions to compare</p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
                <th className="py-2.5 px-3 text-left text-xs font-semibold text-text-muted w-40">
                  Metric
                </th>
                {comparedClients.map((c) => (
                  <th
                    key={c.id}
                    className="py-2.5 px-3 text-left text-xs font-semibold text-text whitespace-nowrap"
                  >
                    {c.name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {COMPARE_ROWS.map((row, i) => {
                const lowerIsBetter = 'lowerIsBetter' in row ? row.lowerIsBetter : false
                const isText = 'isText' in row ? row.isText : false
                const best = isText ? null : getBestValue(row.key, lowerIsBetter)

                return (
                  <tr
                    key={row.key}
                    style={{
                      background: i % 2 === 0 ? 'transparent' : 'var(--color-surface-raised)',
                      borderBottom: '1px solid var(--color-border)',
                    }}
                  >
                    <td className="py-2.5 px-3 text-xs font-medium text-text-muted whitespace-nowrap">
                      {row.label}
                    </td>
                    {comparedClients.map((c) => {
                      const val = getCellValue(c, row.key)
                      const isBest = !isText && val === best
                      return (
                        <td
                          key={c.id}
                          className="py-2.5 px-3 text-xs font-medium tabular-nums"
                          style={{
                            background: isBest ? '#10B98115' : undefined,
                            color: isBest ? '#10B981' : isText ? TIER_COLOR(val as string) : 'var(--color-text)',
                            fontFamily: isText ? undefined : 'var(--font-mono)',
                          }}
                        >
                          {isText ? val : typeof val === 'number' && row.key !== 'missingIndicators'
                            ? `${val}${['griCoverage', 'fraCoverage'].includes(row.key) ? '%' : ''}`
                            : val}
                        </td>
                      )
                    })}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}

// ─── Activity feed ────────────────────────────────────────────────────────────

function ActivityFeed({ items }: { items: ActivityItem[] }) {
  const navigate = useNavigate()
  const setActiveClient = useConsultantStore((s) => s.setActiveClient)
  const clients = MOCK_CLIENTS

  return (
    <Card className="p-5 flex flex-col gap-0" style={{ height: 'fit-content' }}>
      <p className="text-xs font-semibold uppercase tracking-widest text-text-muted mb-4">
        Client Activity
      </p>
      <ul className="flex flex-col gap-3">
        {items.map((item, i) => {
          const client = clients.find((c) => c.id === item.institutionId)
          return (
            <li key={i} className="flex items-start gap-3">
              {/* Institution avatar */}
              <div
                className="w-7 h-7 rounded-lg shrink-0 flex items-center justify-center text-xs font-bold"
                style={{ background: `${item.iconColor}20`, color: item.iconColor }}
              >
                {item.institutionName.slice(0, 2).toUpperCase()}
              </div>

              <div className="flex-1 min-w-0">
                <button
                  onClick={() => {
                    if (client) {
                      setActiveClient({
                        companyId: client.id,
                        companyName: client.name,
                        institutionType: client.type,
                      })
                      navigate('/dashboard')
                    }
                  }}
                  className="text-xs font-semibold hover:underline text-left"
                  style={{ color: 'var(--color-primary)' }}
                >
                  {item.institutionName}
                </button>
                <p className="text-xs text-text-muted leading-snug mt-0.5">{item.action}</p>
              </div>

              <span
                className="text-xs text-text-subtle shrink-0 flex items-center gap-1 mt-0.5"
              >
                <Clock size={10} />
                {item.time}
              </span>
            </li>
          )
        })}
      </ul>
    </Card>
  )
}

// ─── Access denied ────────────────────────────────────────────────────────────

function AccessDenied() {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <div
        className="w-14 h-14 rounded-full flex items-center justify-center mb-5"
        style={{ background: 'var(--color-surface-raised)' }}
      >
        <Users size={24} style={{ color: '#EF4444' }} />
      </div>
      <p className="text-base font-semibold text-text mb-2">Access restricted</p>
      <p className="text-sm text-text-muted mb-6 max-w-sm">
        The Consultant Workspace is only available to consultant and admin accounts.
      </p>
      <Link
        to="/dashboard"
        className="inline-flex items-center gap-2 px-5 py-2.5 text-sm font-semibold rounded transition-colors"
        style={{ background: 'var(--color-primary)', color: '#fff' }}
        onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--color-primary-hover)')}
        onMouseLeave={(e) => (e.currentTarget.style.background = 'var(--color-primary)')}
      >
        Back to Dashboard
      </Link>
    </div>
  )
}

// ─── ConsultantWorkspace ──────────────────────────────────────────────────────

export default function ConsultantWorkspace() {
  const [showAddModal, setShowAddModal] = useState(false)
  const role = useAuthStore((s) => s.role)

  if (role !== 'consultant' && role !== 'admin') {
    return (
      <div className="p-6 max-w-[1400px] mx-auto">
        <AccessDenied />
      </div>
    )
  }

  return (
    <div className="p-6 max-w-[1400px] mx-auto">
      {/* Page header */}
      <div className="flex items-start justify-between mb-6 gap-4">
        <div>
          <h1 className="text-[28px] font-semibold text-text leading-tight">
            Consultant Workspace
          </h1>
          <p className="text-sm text-text-muted mt-1">
            Manage and compare your client portfolio.
          </p>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          <span className="text-xs text-text-muted bg-surface-raised px-3 py-1.5 rounded-full border border-border">
            <span style={{ background: 'var(--color-surface-raised)' }}>
              Managing {MOCK_CLIENTS.length} institutions
            </span>
          </span>
          <button
            onClick={() => setShowAddModal(true)}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-colors"
            style={{ background: 'var(--color-primary)', color: '#fff' }}
            onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--color-primary-hover)')}
            onMouseLeave={(e) => (e.currentTarget.style.background = 'var(--color-primary)')}
          >
            <Plus size={15} />
            Add Client
          </button>
        </div>
      </div>

      {/* Main layout: portfolio grid + activity feed */}
      <div className="flex gap-6">
        {/* Left: grid + comparison */}
        <div className="flex-1 min-w-0 flex flex-col gap-6">
          {/* Client portfolio grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-2 gap-4">
            {MOCK_CLIENTS.map((client) => (
              <ClientCard key={client.id} client={client} />
            ))}
          </div>

          {/* Comparison panel */}
          <ComparisonPanel clients={MOCK_CLIENTS} />
        </div>

        {/* Right: activity feed */}
        <div className="w-[280px] shrink-0 hidden lg:block">
          <ActivityFeed items={MOCK_ACTIVITY} />
        </div>
      </div>

      {showAddModal && <AddClientModal onClose={() => setShowAddModal(false)} />}
    </div>
  )
}
