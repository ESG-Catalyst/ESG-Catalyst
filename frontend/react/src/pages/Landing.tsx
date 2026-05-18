import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { motion, useInView } from 'framer-motion'
import ScoreGauge from '@/components/ui/ScoreGauge'
import { useTranslation } from 'react-i18next'
import { useUIStore } from '@/store/ui'
import { Globe } from 'lucide-react'

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
      }}
    >
      <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
        {/* Wordmark */}
        <Link to="/" className="text-lg font-semibold tracking-tight">
          <span style={{ color: 'var(--color-primary)' }}>ESG</span>
          <span className="text-text"> Catalyst</span>
        </Link>

        {/* Nav links — hidden on mobile */}
        <nav className="hidden md:flex items-center gap-8 text-sm text-text-muted">
          <a href="#how-it-works" className="hover:text-text transition-colors">Features</a>
          <a href="#frameworks" className="hover:text-text transition-colors">Frameworks</a>
          <a href="#pricing" className="hover:text-text transition-colors">Pricing</a>
          <a href="#contact" className="hover:text-text transition-colors">Contact</a>
        </nav>

        {/* Right actions */}
        <div className="flex items-center gap-2">
          <button
            onClick={toggleLang}
            className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs text-text-muted hover:text-text rounded transition-colors"
            title="Switch language / تغيير اللغة"
          >
            <Globe size={13} />
            <span className="font-medium">{language.toUpperCase()}</span>
          </button>
          <Link
            to="/auth/login"
            className="hidden sm:inline-flex items-center px-3.5 py-1.5 text-sm text-text-muted hover:text-text transition-colors rounded"
          >
            Log in
          </Link>
          <Link
            to="/auth/register"
            className="inline-flex items-center px-4 py-1.5 text-sm font-medium rounded transition-colors"
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
      {/* Subtle teal radial glow behind gauge */}
      <div
        className="absolute right-0 top-1/2 -translate-y-1/2 w-[640px] h-[640px] pointer-events-none"
        style={{
          background: 'radial-gradient(circle at 70% 50%, rgba(13,148,136,0.12) 0%, transparent 70%)',
        }}
      />

      <div className="relative max-w-6xl mx-auto grid lg:grid-cols-2 gap-16 items-center">
        {/* Left — copy */}
        <div className="max-w-xl">
          <FadeIn delay={0}>
            <p className="text-sm font-medium mb-4" style={{ color: 'var(--color-primary)' }}>
              Built for Egyptian NBFIs
            </p>
          </FadeIn>
          <FadeIn delay={0.07}>
            <h1 className="text-4xl lg:text-5xl font-semibold leading-tight tracking-tight text-text mb-6">
              ESG Reporting Built for Egyptian Banks
            </h1>
          </FadeIn>
          <FadeIn delay={0.14}>
            <p className="text-lg text-text-muted leading-relaxed mb-10">
              Extract, score, and disclose GRI, FRA, and CBE-aligned ESG metrics from your
              documents — in minutes, not months.
            </p>
          </FadeIn>
          <FadeIn delay={0.2}>
            <div className="flex flex-wrap gap-3">
              <Link
                to="/auth/register"
                className="inline-flex items-center px-6 py-2.5 text-sm font-semibold rounded transition-colors"
                style={{ background: 'var(--color-primary)', color: '#fff' }}
                onMouseEnter={e => (e.currentTarget.style.background = 'var(--color-primary-hover)')}
                onMouseLeave={e => (e.currentTarget.style.background = 'var(--color-primary)')}
              >
                Request Demo
              </Link>
              <a
                href="#how-it-works"
                className="inline-flex items-center px-6 py-2.5 text-sm font-semibold rounded border border-border-subtle text-text-muted hover:text-text hover:border-text-muted transition-colors"
              >
                See How It Works
              </a>
            </div>
          </FadeIn>
        </div>

        {/* Right — animated score gauges */}
        <FadeIn delay={0.1} className="flex justify-center lg:justify-end">
          <ScoreGauge scores={{ E: 72, S: 58, G: 65 }} overall={66} size="lg" />
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
  },
  {
    title: 'FRA Decree 108/2021',
    body: 'Financial Regulatory Authority mandate requiring ESG disclosure from all listed non-banking financial institutions.',
  },
  {
    title: 'GRI Universal Standards',
    body: 'Global Reporting Initiative 2021 framework — the internationally recognised baseline for ESG disclosures.',
  },
]

function RegulatoryStrip() {
  return (
    <section id="frameworks" className="py-16 px-6 border-y border-border">
      <div className="max-w-6xl mx-auto">
        <FadeIn>
          <p className="text-xs font-semibold uppercase tracking-widest text-text-muted mb-8">
            Regulatory Coverage
          </p>
        </FadeIn>
        <div className="grid md:grid-cols-3 gap-4">
          {REGULATIONS.map((reg, i) => (
            <FadeIn key={reg.title} delay={i * 0.08}>
              <div
                className="rounded-lg p-5"
                style={{
                  background: 'var(--color-surface)',
                  borderLeft: '3px solid var(--color-primary)',
                  border: '1px solid var(--color-border)',
                  borderLeftWidth: '3px',
                  borderLeftColor: 'var(--color-primary)',
                }}
              >
                <p className="font-semibold text-text text-sm mb-2">{reg.title}</p>
                <p className="text-text-muted text-xs leading-relaxed">{reg.body}</p>
              </div>
            </FadeIn>
          ))}
        </div>
      </div>
    </section>
  )
}

// ─── How it works ─────────────────────────────────────────────────────────────

const STEPS = [
  {
    n: '01',
    title: 'Upload your documents',
    body: 'Arabic and English PDFs, utility bills, annual reports. The pipeline handles multi-language content natively.',
  },
  {
    n: '02',
    title: 'AI extracts ESG metrics',
    body: 'ClimateBERT classifies relevant passages. An LLM extracts structured values, units, and evidence citations per GRI indicator.',
  },
  {
    n: '03',
    title: 'Download your disclosure',
    body: 'Receive a GRI content index, FRA-compliant PDF report, and machine-readable metric export — ready to file.',
  },
]

function HowItWorks() {
  return (
    <section id="how-it-works" className="py-20 px-6">
      <div className="max-w-6xl mx-auto">
        <FadeIn>
          <h2 className="text-2xl font-semibold text-text mb-2">How it works</h2>
          <p className="text-text-muted text-sm mb-14">Three steps from document upload to regulatory disclosure.</p>
        </FadeIn>

        <div className="relative">
          {/* Vertical connector line */}
          <div
            className="absolute left-[19px] top-8 bottom-8 w-px hidden md:block"
            style={{ background: 'linear-gradient(to bottom, var(--color-primary), transparent)' }}
          />

          <div className="flex flex-col gap-10">
            {STEPS.map((step, i) => (
              <FadeIn key={step.n} delay={i * 0.1}>
                <div className="flex gap-6 items-start">
                  {/* Step number bubble */}
                  <div
                    className="shrink-0 w-10 h-10 rounded-full flex items-center justify-center text-xs font-bold z-10"
                    style={{
                      background: 'var(--color-surface)',
                      border: '2px solid var(--color-primary)',
                      color: 'var(--color-primary)',
                      fontFamily: 'var(--font-mono)',
                    }}
                  >
                    {step.n}
                  </div>
                  <div className="pt-1.5">
                    <p className="font-semibold text-text mb-1">{step.title}</p>
                    <p className="text-text-muted text-sm leading-relaxed max-w-lg">{step.body}</p>
                  </div>
                </div>
              </FadeIn>
            ))}
          </div>
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
    <section className="py-16 px-6" style={{ background: 'var(--color-surface)' }}>
      <div className="max-w-6xl mx-auto grid sm:grid-cols-2 lg:grid-cols-4 gap-px" style={{ background: 'var(--color-border)' }}>
        {STATS.map((stat, i) => (
          <FadeIn key={stat.label} delay={i * 0.07}>
            <div className="px-8 py-8" style={{ background: 'var(--color-surface)' }}>
              <p
                className="text-3xl font-semibold mb-2"
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

function Pricing() {
  return (
    <section id="pricing" className="py-24 px-6">
      <div className="max-w-6xl mx-auto">
        <FadeIn>
          <h2 className="text-2xl font-semibold text-text mb-2">Pricing</h2>
          <p className="text-text-muted text-sm mb-14 max-w-lg">
            Transparent pricing built for Egyptian financial institutions.
            All plans include a 14-day free trial — no credit card required.
          </p>
        </FadeIn>

        <div className="grid md:grid-cols-3 gap-6 items-start">
          {PLANS.map((plan, i) => (
            <FadeIn key={plan.name} delay={i * 0.08}>
              <div
                className="rounded-xl p-7 flex flex-col gap-6 h-full relative"
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
                    className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-0.5 rounded-full text-xs font-bold tracking-wide"
                    style={{ background: '#fff', color: 'var(--color-primary)' }}
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
                    className="text-sm ml-1"
                    style={{ color: plan.highlight ? 'rgba(255,255,255,0.65)' : 'var(--color-text-muted)' }}
                  >
                    {plan.period}
                  </span>
                </div>

                {/* Features */}
                <ul className="flex flex-col gap-2.5 flex-1">
                  {plan.features.map((f) => (
                    <li key={f} className="flex items-start gap-2.5 text-sm">
                      <svg
                        width={14}
                        height={14}
                        viewBox="0 0 14 14"
                        fill="none"
                        className="mt-0.5 shrink-0"
                      >
                        <circle
                          cx="7"
                          cy="7"
                          r="7"
                          fill={plan.highlight ? 'rgba(255,255,255,0.2)' : 'rgba(13,148,136,0.15)'}
                        />
                        <path
                          d="M4 7l2 2 4-4"
                          stroke={plan.highlight ? '#fff' : 'var(--color-primary)'}
                          strokeWidth={1.5}
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                      </svg>
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
                    className="mt-2 w-full py-2.5 text-sm font-semibold rounded text-center transition-colors block"
                    style={
                      plan.highlight
                        ? { background: '#fff', color: 'var(--color-primary)' }
                        : { background: 'var(--color-surface-raised)', color: 'var(--color-text)' }
                    }
                  >
                    {plan.cta}
                  </a>
                ) : (
                  <a
                    href={plan.ctaTo}
                    className="mt-2 w-full py-2.5 text-sm font-semibold rounded text-center transition-colors block"
                    style={
                      plan.highlight
                        ? { background: '#fff', color: 'var(--color-primary)' }
                        : { background: 'var(--color-surface-raised)', color: 'var(--color-text)' }
                    }
                  >
                    {plan.cta}
                  </a>
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
    >
      <div className="max-w-6xl mx-auto grid md:grid-cols-2 gap-12 items-center">
        <FadeIn>
          <h2 className="text-2xl font-semibold text-text mb-3">Get in touch</h2>
          <p className="text-text-muted text-sm leading-relaxed mb-6">
            Interested in ESG Catalyst for your institution? We'll walk you through a live demo
            using your own documents and show you exactly what we extract.
          </p>
          <div className="flex flex-col gap-3 text-sm text-text-muted">
            <span>📍 Cairo, Egypt</span>
            <span>✉️ hello@esgcatalyst.io</span>
            <span>🌐 Available in Arabic and English</span>
          </div>
        </FadeIn>
        <FadeIn delay={0.1}>
          <div
            className="rounded-xl p-7"
            style={{ background: 'var(--color-bg)', border: '1px solid var(--color-border)' }}
          >
            <div className="flex flex-col gap-4">
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-semibold text-text-muted">Name</label>
                <input
                  type="text"
                  placeholder="Your name"
                  className="w-full px-3 py-2 text-sm rounded outline-none transition-all"
                  style={{
                    background: 'var(--color-surface)',
                    border: '1px solid var(--color-border)',
                    color: 'var(--color-text)',
                  }}
                  onFocus={(e) => (e.currentTarget.style.borderColor = 'var(--color-primary)')}
                  onBlur={(e) => (e.currentTarget.style.borderColor = 'var(--color-border)')}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-semibold text-text-muted">Institution</label>
                <input
                  type="text"
                  placeholder="Bank / NBFI name"
                  className="w-full px-3 py-2 text-sm rounded outline-none transition-all"
                  style={{
                    background: 'var(--color-surface)',
                    border: '1px solid var(--color-border)',
                    color: 'var(--color-text)',
                  }}
                  onFocus={(e) => (e.currentTarget.style.borderColor = 'var(--color-primary)')}
                  onBlur={(e) => (e.currentTarget.style.borderColor = 'var(--color-border)')}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-semibold text-text-muted">Email</label>
                <input
                  type="email"
                  placeholder="you@institution.com"
                  className="w-full px-3 py-2 text-sm rounded outline-none transition-all"
                  style={{
                    background: 'var(--color-surface)',
                    border: '1px solid var(--color-border)',
                    color: 'var(--color-text)',
                  }}
                  onFocus={(e) => (e.currentTarget.style.borderColor = 'var(--color-primary)')}
                  onBlur={(e) => (e.currentTarget.style.borderColor = 'var(--color-border)')}
                />
              </div>
              <button
                className="mt-1 w-full py-2.5 text-sm font-semibold rounded transition-colors"
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
        <h2 className="text-2xl font-semibold text-text mb-4">
          Ready to file your ESG disclosure?
        </h2>
        <p className="text-text-muted text-sm mb-8 max-w-md mx-auto">
          Join Egyptian financial institutions that have moved from manual spreadsheets to
          automated, auditable ESG reporting.
        </p>
        <Link
          to="/auth/register"
          className="inline-flex items-center px-8 py-3 text-sm font-semibold rounded transition-colors"
          style={{ background: 'var(--color-primary)', color: '#fff' }}
          onMouseEnter={e => (e.currentTarget.style.background = 'var(--color-primary-hover)')}
          onMouseLeave={e => (e.currentTarget.style.background = 'var(--color-primary)')}
        >
          Get Started
        </Link>
      </FadeIn>
    </section>
  )
}

// ─── Footer ───────────────────────────────────────────────────────────────────

function Footer() {
  return (
    <footer
      className="py-8 px-6 text-center text-xs text-text-subtle border-t"
      style={{ borderColor: 'var(--color-border)' }}
    >
      <span>ESG Catalyst — Confidential. Not for distribution.</span>
    </footer>
  )
}

// ─── Page export ──────────────────────────────────────────────────────────────

export default function Landing() {
  return (
    <div className="min-h-screen" style={{ background: 'var(--color-bg)' }}>
      <Navbar />
      <Hero />
      <RegulatoryStrip />
      <HowItWorks />
      <Stats />
      <Pricing />
      <Contact />
      <BottomCTA />
      <Footer />
    </div>
  )
}
