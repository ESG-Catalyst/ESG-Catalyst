import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { motion, useInView } from 'framer-motion'
import ScoreGauge from '@/components/ui/ScoreGauge'
import { useTranslation } from 'react-i18next'
import { useUIStore } from '@/store/ui'
import { Globe, Shield, Zap, FileCheck, ArrowRight, CheckCircle2 } from 'lucide-react'

// ─── Navbar ──────────────────────────────────────────────────────────────────

function Navbar() {
  const [scrolled, setScrolled] = useState(false)
  const { language, setLanguage } = useUIStore()
  const { i18n } = useTranslation()

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 12)
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  function toggleLang() {
    const next = language === 'en' ? 'ar' : 'en'
    setLanguage(next)
    i18n.changeLanguage(next)
    document.documentElement.lang = next
    document.documentElement.dir = next === 'ar' ? 'rtl' : 'ltr'
  }

  return (
    <header
      className="fixed top-0 inset-x-0 z-50 transition-all duration-200"
      style={{
        background: scrolled ? 'var(--color-surface)' : 'transparent',
        borderBottom: scrolled ? '1px solid var(--color-border)' : '1px solid transparent',
        backdropFilter: scrolled ? 'blur(12px)' : 'none',
      }}
    >
      <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
        {/* Wordmark */}
        <Link to="/" className="text-lg font-semibold tracking-tight focus-visible:ring-2 ring-primary rounded">
          <span style={{ color: 'var(--color-primary)' }}>ESG</span>
          <span className="text-text"> Catalyst</span>
        </Link>

        {/* Nav links — hidden on mobile */}
        <nav className="hidden md:flex items-center gap-8 text-sm text-text-muted" aria-label="Main navigation">
          <a href="#how-it-works" className="hover:text-text transition-colors focus-visible:ring-2 ring-primary rounded px-1">Features</a>
          <a href="#frameworks" className="hover:text-text transition-colors focus-visible:ring-2 ring-primary rounded px-1">Frameworks</a>
          <a href="#pricing" className="hover:text-text transition-colors focus-visible:ring-2 ring-primary rounded px-1">Pricing</a>
          <a href="#contact" className="hover:text-text transition-colors focus-visible:ring-2 ring-primary rounded px-1">Contact</a>
        </nav>

        {/* Right actions */}
        <div className="flex items-center gap-2">
          <button
            onClick={toggleLang}
            className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs text-text-muted hover:text-text rounded transition-colors focus-visible:ring-2 ring-primary"
            aria-label="Switch language / تغيير اللغة"
          >
            <Globe size={13} aria-hidden="true" />
            <span className="font-medium">{language.toUpperCase()}</span>
          </button>
          <Link
            to="/auth/login"
            className="hidden sm:inline-flex items-center px-3.5 py-1.5 text-sm text-text-muted hover:text-text transition-colors rounded focus-visible:ring-2 ring-primary"
          >
            Log in
          </Link>
          <Link
            to="/auth/register"
            className="inline-flex items-center px-4 py-1.5 text-sm font-medium rounded transition-colors focus-visible:ring-2 ring-primary"
            style={{ background: 'var(--color-primary)', color: '#fff' }}
            onMouseEnter={e => (e.currentTarget.style.background = 'var(--color-primary-hover)')}
            onMouseLeave={e => (e.currentTarget.style.background = 'var(--color-primary)')}
          >
            Get Started
          </Link>
        </div>
      </div>
    </header>
  )
}

// ─── Section fade-in wrapper ──────────────────────────────────────────────────

function FadeIn({ children, delay = 0, className = '' }: {
  children: React.ReactNode
  delay?: number
  className?: string
}) {
  const ref = useRef(null)
  const inView = useInView(ref, { once: true, margin: '-40px' })
  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, y: 20 }}
      animate={inView ? { opacity: 1, y: 0 } : {}}
      transition={{ duration: 0.5, delay, ease: 'easeOut' }}
      className={className}
    >
      {children}
    </motion.div>
  )
}

// ─── Hero ─────────────────────────────────────────────────────────────────────

function Hero() {
  return (
    <section className="relative pt-32 pb-24 px-6 overflow-hidden">
      {/* Layered radial glows for depth */}
      <div
        className="absolute end-0 top-1/2 -translate-y-1/2 w-[640px] h-[640px] pointer-events-none"
        aria-hidden="true"
        style={{
          background: 'radial-gradient(circle at 70% 50%, rgba(13,148,136,0.12) 0%, transparent 70%)',
        }}
      />
      <div
        className="absolute start-0 bottom-0 w-[400px] h-[400px] pointer-events-none"
        aria-hidden="true"
        style={{
          background: 'radial-gradient(circle at 30% 80%, rgba(13,148,136,0.06) 0%, transparent 70%)',
        }}
      />

      <div className="relative max-w-6xl mx-auto grid lg:grid-cols-2 gap-16 items-center">
        {/* Left — copy */}
        <div className="max-w-xl">
          {/* Trust badge */}
          <FadeIn delay={0}>
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-semibold mb-6"
              style={{ background: 'rgba(13,148,136,0.12)', border: '1px solid rgba(13,148,136,0.25)', color: 'var(--color-primary)' }}
            >
              <Shield size={11} aria-hidden="true" />
              FRA · CBE · GRI Aligned
            </div>
          </FadeIn>
          <FadeIn delay={0.07}>
            <h1 className="text-4xl lg:text-5xl font-semibold leading-tight tracking-tight text-text mb-6">
              ESG Reporting Built for Egyptian Banks
            </h1>
          </FadeIn>
          <FadeIn delay={0.14}>
            <p className="text-lg text-text-muted leading-relaxed mb-8">
              Extract, score, and disclose GRI, FRA, and CBE-aligned ESG metrics from your
              documents — in minutes, not months.
            </p>
          </FadeIn>

          {/* Social proof / trust signals */}
          <FadeIn delay={0.18}>
            <ul className="flex flex-col gap-2 mb-10" aria-label="Key features">
              {[
                'Arabic and English document support',
                '46 GRI + SASB + FRA indicators scored automatically',
                'AI extraction with per-metric confidence scoring',
              ].map((item) => (
                <li key={item} className="flex items-center gap-2.5 text-sm text-text-muted">
                  <CheckCircle2 size={14} style={{ color: 'var(--color-primary)' }} className="shrink-0" aria-hidden="true" />
                  {item}
                </li>
              ))}
            </ul>
          </FadeIn>

          <FadeIn delay={0.22}>
            <div className="flex flex-wrap gap-3">
              <Link
                to="/auth/register"
                className="inline-flex items-center gap-2 px-6 py-2.5 text-sm font-semibold rounded transition-colors focus-visible:ring-2 ring-primary ring-offset-2"
                style={{ background: 'var(--color-primary)', color: '#fff' }}
                onMouseEnter={e => (e.currentTarget.style.background = 'var(--color-primary-hover)')}
                onMouseLeave={e => (e.currentTarget.style.background = 'var(--color-primary)')}
              >
                Request Demo
                <ArrowRight size={14} aria-hidden="true" />
              </Link>
              <a
                href="#how-it-works"
                className="inline-flex items-center px-6 py-2.5 text-sm font-semibold rounded border border-border-subtle text-text-muted hover:text-text hover:border-text-muted transition-colors focus-visible:ring-2 ring-primary"
              >
                See How It Works
              </a>
            </div>
          </FadeIn>
        </div>

        {/* Right — animated score gauges */}
        <FadeIn delay={0.1} className="flex justify-center lg:justify-end">
          <div className="relative">
            <div
              className="absolute inset-0 rounded-2xl pointer-events-none"
              aria-hidden="true"
              style={{ background: 'radial-gradient(circle at 50% 50%, rgba(13,148,136,0.08) 0%, transparent 70%)' }}
            />
            <ScoreGauge scores={{ E: 72, S: 58, G: 65 }} overall={66} size="lg" />
          </div>
        </FadeIn>
      </div>
    </section>
  )
}

// ─── Regulatory context strip ─────────────────────────────────────────────────

const REGULATIONS = [
  {
    title: 'CBE Sustainable Finance Guidelines',
    body: 'Central Bank of Egypt directive requiring banks to integrate ESG risk into credit decisions and disclosures.',
    icon: Shield,
  },
  {
    title: 'FRA Decree 108/2021',
    body: 'Financial Regulatory Authority mandate requiring ESG disclosure from all listed non-banking financial institutions.',
    icon: FileCheck,
  },
  {
    title: 'GRI Universal Standards',
    body: 'Global Reporting Initiative 2021 framework — the internationally recognised baseline for ESG disclosures.',
    icon: CheckCircle2,
  },
]

function RegulatoryStrip() {
  return (
    <section id="frameworks" className="py-16 px-6 border-y border-border" aria-labelledby="frameworks-heading">
      <div className="max-w-6xl mx-auto">
        <FadeIn>
          <p id="frameworks-heading" className="text-xs font-semibold uppercase tracking-widest text-text-muted mb-8">
            Regulatory Coverage
          </p>
        </FadeIn>
        <div className="grid md:grid-cols-3 gap-4">
          {REGULATIONS.map((reg, i) => {
            const Icon = reg.icon
            return (
              <FadeIn key={reg.title} delay={i * 0.08}>
                <div
                  className="rounded-xl p-5 flex flex-col gap-3 h-full transition-all hover:scale-[1.01]"
                  style={{
                    background: 'var(--color-surface)',
                    border: '1px solid var(--color-border)',
                    borderInlineStartWidth: '3px',
                    borderInlineStartColor: 'var(--color-primary)',
                  }}
                >
                  <div className="flex items-start gap-3">
                    <div
                      className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0 mt-0.5"
                      style={{ background: 'rgba(13,148,136,0.12)' }}
                    >
                      <Icon size={15} style={{ color: 'var(--color-primary)' }} aria-hidden="true" />
                    </div>
                    <p className="font-semibold text-text text-sm leading-snug">{reg.title}</p>
                  </div>
                  <p className="text-text-muted text-xs leading-relaxed">{reg.body}</p>
                </div>
              </FadeIn>
            )
          })}
        </div>
      </div>
    </section>
  )
}

// ─── How it works ─────────────────────────────────────────────────────────────

const STEPS = [
  {
    n: '01',
    icon: FileCheck,
    title: 'Upload your documents',
    body: 'Arabic and English PDFs, utility bills, annual reports. The pipeline handles multi-language content natively.',
  },
  {
    n: '02',
    icon: Zap,
    title: 'AI extracts ESG metrics',
    body: 'ClimateBERT classifies relevant passages. An LLM extracts structured values, units, and evidence citations per GRI indicator.',
  },
  {
    n: '03',
    icon: CheckCircle2,
    title: 'Download your disclosure',
    body: 'Receive a GRI content index, FRA-compliant PDF report, and machine-readable metric export — ready to file.',
  },
]

function HowItWorks() {
  return (
    <section id="how-it-works" className="py-20 px-6" aria-labelledby="how-it-works-heading">
      <div className="max-w-6xl mx-auto">
        <FadeIn>
          <h2 id="how-it-works-heading" className="text-2xl font-semibold text-text mb-2">How it works</h2>
          <p className="text-text-muted text-sm mb-14">Three steps from document upload to regulatory disclosure.</p>
        </FadeIn>

        <div className="grid md:grid-cols-3 gap-8">
          {STEPS.map((step, i) => {
            const Icon = step.icon
            return (
              <FadeIn key={step.n} delay={i * 0.1}>
                <div className="flex flex-col gap-4">
                  <div className="flex items-center gap-3">
                    <div
                      className="w-10 h-10 rounded-full flex items-center justify-center text-xs font-bold shrink-0"
                      style={{
                        background: 'var(--color-surface)',
                        border: '2px solid var(--color-primary)',
                        color: 'var(--color-primary)',
                        fontFamily: 'var(--font-mono)',
                      }}
                      aria-hidden="true"
                    >
                      {step.n}
                    </div>
                    <div
                      className="w-9 h-9 rounded-lg flex items-center justify-center"
                      style={{ background: 'rgba(13,148,136,0.1)' }}
                    >
                      <Icon size={17} style={{ color: 'var(--color-primary)' }} aria-hidden="true" />
                    </div>
                  </div>
                  <div>
                    <p className="font-semibold text-text mb-1.5">{step.title}</p>
                    <p className="text-text-muted text-sm leading-relaxed">{step.body}</p>
                  </div>
                </div>
              </FadeIn>
            )
          })}
        </div>

        {/* Connector line between steps on desktop — decorative */}
        <div className="hidden md:flex items-center justify-between mt-0 -mb-8 pointer-events-none" aria-hidden="true">
          <div className="flex-1 h-px mx-8 mt-5" style={{ background: 'linear-gradient(to end, var(--color-primary), transparent)' }} />
        </div>
      </div>
    </section>
  )
}

// ─── Key metrics / stats ──────────────────────────────────────────────────────

const STATS = [
  { value: '46', label: 'GRI, FRA & SASB indicators scored' },
  { value: 'AR + EN', label: 'Arabic and English document support' },
  { value: '3', label: 'Frameworks: GRI / FRA / SASB' },
  { value: '0–1', label: 'Confidence score per extracted metric' },
]

function Stats() {
  return (
    <section className="py-16 px-6" style={{ background: 'var(--color-surface)' }} aria-label="Platform statistics">
      <div className="max-w-6xl mx-auto grid sm:grid-cols-2 lg:grid-cols-4 gap-px" style={{ background: 'var(--color-border)' }}>
        {STATS.map((stat, i) => (
          <FadeIn key={stat.label} delay={i * 0.07}>
            <div className="px-8 py-8 group" style={{ background: 'var(--color-surface)' }}>
              <p
                className="text-3xl font-semibold mb-2 transition-transform duration-200 group-hover:scale-105"
                style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-primary)' }}
              >
                {stat.value}
              </p>
              <p className="text-sm text-text-muted leading-snug">{stat.label}</p>
            </div>
          </FadeIn>
        ))}
      </div>
    </section>
  )
}

// ─── Pricing ──────────────────────────────────────────────────────────────────

const PLANS = [
  {
    name: 'Starter',
    price: 'EGP 4,500',
    period: '/mo',
    description: 'For single NBFIs starting their ESG journey.',
    highlight: false,
    cta: 'Get Started',
    ctaTo: '/auth/register',
    features: [
      '1 company profile',
      'Up to 5 document uploads/month',
      '13 core GRI indicators',
      'PDF disclosure report',
      'FRA framework coverage',
      'Email support',
    ],
  },
  {
    name: 'Professional',
    price: 'EGP 14,900',
    period: '/mo',
    description: 'For growing banks and NBFIs that need full coverage.',
    highlight: true,
    cta: 'Start Free Trial',
    ctaTo: '/auth/register',
    features: [
      '1 company profile',
      'Unlimited document uploads',
      'All 46 GRI + FRA + SASB indicators',
      'Arabic & English document support',
      'Metric review & approval workflow',
      'MLflow confidence tracking',
      'Priority support',
    ],
  },
  {
    name: 'Consultant',
    price: 'EGP 39,000',
    period: '/mo',
    description: 'For advisory firms managing multiple client portfolios.',
    highlight: false,
    cta: 'Contact Us',
    ctaTo: '#contact',
    features: [
      'Up to 20 client companies',
      'Unified consultant dashboard',
      'Bulk document processing',
      'All 46 GRI + FRA + SASB indicators',
      'White-label PDF reports',
      'Benchmark comparisons across clients',
      'Dedicated account manager',
    ],
  },
]

function CheckIcon({ highlight }: { highlight: boolean }) {
  return (
    <svg
      width={14}
      height={14}
      viewBox="0 0 14 14"
      fill="none"
      className="mt-0.5 shrink-0"
      aria-hidden="true"
    >
      <circle
        cx="7"
        cy="7"
        r="7"
        fill={highlight ? 'rgba(255,255,255,0.2)' : 'rgba(13,148,136,0.15)'}
      />
      <path
        d="M4 7l2 2 4-4"
        stroke={highlight ? '#fff' : 'var(--color-primary)'}
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function Pricing() {
  return (
    <section id="pricing" className="py-24 px-6" aria-labelledby="pricing-heading">
      <div className="max-w-6xl mx-auto">
        <FadeIn>
          <h2 id="pricing-heading" className="text-2xl font-semibold text-text mb-2">Pricing</h2>
          <p className="text-text-muted text-sm mb-14 max-w-lg">
            Transparent pricing built for Egyptian financial institutions.
            All plans include a 14-day free trial — no credit card required.
          </p>
        </FadeIn>

        <div className="grid md:grid-cols-3 gap-6 items-start">
          {PLANS.map((plan, i) => (
            <FadeIn key={plan.name} delay={i * 0.08}>
              <div
                className="rounded-xl p-7 flex flex-col gap-6 h-full relative transition-transform duration-200 hover:-translate-y-1"
                style={{
                  background: plan.highlight ? 'var(--color-primary)' : 'var(--color-surface)',
                  border: plan.highlight
                    ? '1.5px solid var(--color-primary)'
                    : '1px solid var(--color-border)',
                  boxShadow: plan.highlight ? '0 8px 32px rgba(13,148,136,0.25)' : undefined,
                }}
              >
                {plan.highlight && (
                  <div
                    className="absolute -top-3 start-1/2 -translate-x-1/2 px-3 py-0.5 rounded-full text-xs font-bold tracking-wide"
                    style={{ background: '#fff', color: 'var(--color-primary)' }}
                    aria-label="Most popular plan"
                  >
                    Most Popular
                  </div>
                )}

                {/* Plan name + description */}
                <div>
                  <p
                    className="text-xs font-bold uppercase tracking-widest mb-2"
                    style={{ color: plan.highlight ? 'rgba(255,255,255,0.75)' : 'var(--color-primary)' }}
                  >
                    {plan.name}
                  </p>
                  <p
                    className="text-sm leading-snug"
                    style={{ color: plan.highlight ? 'rgba(255,255,255,0.8)' : 'var(--color-text-muted)' }}
                  >
                    {plan.description}
                  </p>
                </div>

                {/* Price */}
                <div>
                  <span
                    className="text-3xl font-semibold"
                    style={{
                      fontFamily: 'var(--font-mono)',
                      color: plan.highlight ? '#fff' : 'var(--color-text)',
                    }}
                  >
                    {plan.price}
                  </span>
                  <span
                    className="text-sm ms-1"
                    style={{ color: plan.highlight ? 'rgba(255,255,255,0.65)' : 'var(--color-text-muted)' }}
                  >
                    {plan.period}
                  </span>
                </div>

                {/* Features */}
                <ul className="flex flex-col gap-2.5 flex-1" aria-label={`${plan.name} plan features`}>
                  {plan.features.map((f) => (
                    <li key={f} className="flex items-start gap-2.5 text-sm">
                      <CheckIcon highlight={plan.highlight} />
                      <span style={{ color: plan.highlight ? 'rgba(255,255,255,0.9)' : 'var(--color-text-muted)' }}>
                        {f}
                      </span>
                    </li>
                  ))}
                </ul>

                {/* CTA */}
                {plan.ctaTo.startsWith('#') ? (
                  <a
                    href={plan.ctaTo}
                    className="mt-2 w-full py-2.5 text-sm font-semibold rounded text-center transition-colors block focus-visible:ring-2 ring-primary ring-offset-1"
                    style={
                      plan.highlight
                        ? { background: '#fff', color: 'var(--color-primary)' }
                        : { background: 'var(--color-surface-raised)', color: 'var(--color-text)' }
                    }
                  >
                    {plan.cta}
                  </a>
                ) : (
                  <Link
                    to={plan.ctaTo}
                    className="mt-2 w-full py-2.5 text-sm font-semibold rounded text-center transition-colors block focus-visible:ring-2 ring-primary ring-offset-1"
                    style={
                      plan.highlight
                        ? { background: '#fff', color: 'var(--color-primary)' }
                        : { background: 'var(--color-surface-raised)', color: 'var(--color-text)' }
                    }
                  >
                    {plan.cta}
                  </Link>
                )}
              </div>
            </FadeIn>
          ))}
        </div>

        <FadeIn delay={0.25}>
          <p className="mt-10 text-center text-xs text-text-subtle">
            All prices are VAT-exclusive. Annual plans available at 20% discount.
            Custom enterprise pricing for 20+ companies — <a href="#contact" className="underline hover:text-text-muted transition-colors">contact us</a>.
          </p>
        </FadeIn>
      </div>
    </section>
  )
}

// ─── Contact ──────────────────────────────────────────────────────────────────

function Contact() {
  return (
    <section
      id="contact"
      className="py-20 px-6"
      style={{ background: 'var(--color-surface)', borderTop: '1px solid var(--color-border)' }}
      aria-labelledby="contact-heading"
    >
      <div className="max-w-6xl mx-auto grid md:grid-cols-2 gap-12 items-center">
        <FadeIn>
          <h2 id="contact-heading" className="text-2xl font-semibold text-text mb-3">Get in touch</h2>
          <p className="text-text-muted text-sm leading-relaxed mb-6">
            Interested in ESG Catalyst for your institution? We'll walk you through a live demo
            using your own documents and show you exactly what we extract.
          </p>
          <div className="flex flex-col gap-3 text-sm text-text-muted">
            <span className="flex items-center gap-2">
              <span aria-hidden="true">📍</span>
              Cairo, Egypt
            </span>
            <span className="flex items-center gap-2">
              <span aria-hidden="true">✉️</span>
              hello@esgcatalyst.io
            </span>
            <span className="flex items-center gap-2">
              <span aria-hidden="true">🌐</span>
              Available in Arabic and English
            </span>
          </div>
        </FadeIn>
        <FadeIn delay={0.1}>
          <div
            className="rounded-xl p-7"
            style={{ background: 'var(--color-bg)', border: '1px solid var(--color-border)' }}
          >
            <div className="flex flex-col gap-4">
              {[
                { label: 'Name', type: 'text', placeholder: 'Your name', autoComplete: 'name' },
                { label: 'Institution', type: 'text', placeholder: 'Bank / NBFI name', autoComplete: 'organization' },
                { label: 'Email', type: 'email', placeholder: 'you@institution.com', autoComplete: 'email' },
              ].map((field) => (
                <div key={field.label} className="flex flex-col gap-1.5">
                  <label className="text-xs font-semibold text-text-muted" htmlFor={`contact-${field.label.toLowerCase()}`}>
                    {field.label}
                  </label>
                  <input
                    id={`contact-${field.label.toLowerCase()}`}
                    type={field.type}
                    placeholder={field.placeholder}
                    autoComplete={field.autoComplete}
                    className="w-full px-3 py-2 text-sm rounded outline-none transition-all focus-visible:ring-2 ring-primary"
                    style={{
                      background: 'var(--color-surface)',
                      border: '1px solid var(--color-border)',
                      color: 'var(--color-text)',
                    }}
                    onFocus={(e) => (e.currentTarget.style.borderColor = 'var(--color-primary)')}
                    onBlur={(e) => (e.currentTarget.style.borderColor = 'var(--color-border)')}
                  />
                </div>
              ))}
              <button
                className="mt-1 w-full py-2.5 text-sm font-semibold rounded transition-colors focus-visible:ring-2 ring-primary ring-offset-1"
                style={{ background: 'var(--color-primary)', color: '#fff' }}
                onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--color-primary-hover)')}
                onMouseLeave={(e) => (e.currentTarget.style.background = 'var(--color-primary)')}
                onClick={() => alert('Thanks! We\'ll reach out within 24 hours.')}
              >
                Request Demo
              </button>
            </div>
          </div>
        </FadeIn>
      </div>
    </section>
  )
}

// ─── Bottom CTA ───────────────────────────────────────────────────────────────

function BottomCTA() {
  return (
    <section className="py-24 px-6 text-center">
      <FadeIn>
        {/* Decorative teal ring */}
        <div
          className="w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-6"
          style={{ background: 'rgba(13,148,136,0.1)', border: '1px solid rgba(13,148,136,0.2)' }}
          aria-hidden="true"
        >
          <Zap size={24} style={{ color: 'var(--color-primary)' }} />
        </div>
        <h2 className="text-2xl font-semibold text-text mb-4">
          Ready to file your ESG disclosure?
        </h2>
        <p className="text-text-muted text-sm mb-8 max-w-md mx-auto">
          Join Egyptian financial institutions that have moved from manual spreadsheets to
          automated, auditable ESG reporting.
        </p>
        <div className="flex flex-wrap items-center justify-center gap-4">
          <Link
            to="/auth/register"
            className="inline-flex items-center gap-2 px-8 py-3 text-sm font-semibold rounded transition-colors focus-visible:ring-2 ring-primary ring-offset-2"
            style={{ background: 'var(--color-primary)', color: '#fff' }}
            onMouseEnter={e => (e.currentTarget.style.background = 'var(--color-primary-hover)')}
            onMouseLeave={e => (e.currentTarget.style.background = 'var(--color-primary)')}
          >
            Get Started Free
            <ArrowRight size={14} aria-hidden="true" />
          </Link>
          <a
            href="#contact"
            className="text-sm text-text-muted hover:text-text transition-colors underline underline-offset-4 focus-visible:ring-2 ring-primary rounded"
          >
            Talk to an expert
          </a>
        </div>
      </FadeIn>
    </section>
  )
}

// ─── Footer ───────────────────────────────────────────────────────────────────

function Footer() {
  return (
    <footer
      className="py-8 px-6 border-t"
      style={{ borderColor: 'var(--color-border)' }}
    >
      <div className="max-w-6xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-text-subtle">
        <span>ESG Catalyst — Confidential. Not for distribution.</span>
        <div className="flex items-center gap-4">
          <a href="#frameworks" className="hover:text-text-muted transition-colors">Frameworks</a>
          <a href="#pricing" className="hover:text-text-muted transition-colors">Pricing</a>
          <a href="#contact" className="hover:text-text-muted transition-colors">Contact</a>
        </div>
      </div>
    </footer>
  )
}

// ─── Page export ──────────────────────────────────────────────────────────────

export default function Landing() {
  return (
    <div className="min-h-screen" style={{ background: 'var(--color-bg)' }}>
      <Navbar />
      <main>
        <Hero />
        <RegulatoryStrip />
        <HowItWorks />
        <Stats />
        <Pricing />
        <Contact />
        <BottomCTA />
      </main>
      <Footer />
    </div>
  )
}
