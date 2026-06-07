import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { motion, useInView } from 'framer-motion'
import ScoreGauge from '@/components/ui/ScoreGauge'
import { useTranslation } from 'react-i18next'
import { useUIStore } from '@/store/ui'
import { useAuthStore, emailInitials } from '@/store/auth'
import {
  Globe, Shield, Zap, FileCheck, ArrowRight, CheckCircle2,
  Sun, Moon, Layers, Sparkles, BarChart3,
} from 'lucide-react'

// ─── Shared helpers ───────────────────────────────────────────────────────────

/** Smooth-scroll to an in-page section, accounting for the fixed navbar. */
function scrollToId(e: React.MouseEvent, id: string) {
  const el = document.getElementById(id)
  if (el) {
    e.preventDefault()
    el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
}

/**
 * "Talk to an expert" / "Consultant" flow: if the visitor is signed in, jump
 * straight to the contact section; otherwise send them to register first and
 * bounce them back to the contact section after signup (?next=/#contact).
 */
function useContactCTA() {
  const token = useAuthStore((s) => s.token)
  const navigate = useNavigate()
  return (e?: React.MouseEvent) => {
    e?.preventDefault()
    if (token) {
      document.getElementById('contact')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    } else {
      navigate('/auth/register?next=' + encodeURIComponent('/#contact'))
    }
  }
}

function confidenceColor(c: number): string {
  if (c >= 90) return '#10B981'
  if (c >= 75) return '#0D9488'
  return '#F59E0B'
}

// ─── Navbar ──────────────────────────────────────────────────────────────────

function Navbar() {
  const [scrolled, setScrolled] = useState(false)
  const { language, setLanguage, theme, toggleTheme } = useUIStore()
  const { t, i18n } = useTranslation()
  const token = useAuthStore((s) => s.token)
  const email = useAuthStore((s) => s.email)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 12)
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  // Keep i18n in sync with the persisted store language (fixes Arabic content
  // staying English when the page loads RTL).
  useEffect(() => {
    if (i18n.language !== language) i18n.changeLanguage(language)
  }, [language, i18n])

  function toggleLang() {
    const next = language === 'en' ? 'ar' : 'en'
    setLanguage(next)            // applies dir/lang + Arabic font via the store
    i18n.changeLanguage(next)   // flips the translated copy
  }

  const navLinks = [
    { id: 'how-it-works', label: t('landing.nav_features') },
    { id: 'frameworks', label: t('landing.nav_frameworks') },
    { id: 'pricing', label: t('landing.nav_pricing') },
    { id: 'contact', label: t('landing.nav_contact') },
  ]

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
          {navLinks.map((link) => (
            <a
              key={link.id}
              href={`#${link.id}`}
              onClick={(e) => scrollToId(e, link.id)}
              className="hover:text-text transition-colors focus-visible:ring-2 ring-primary rounded px-1"
            >
              {link.label}
            </a>
          ))}
        </nav>

        {/* Right actions */}
        <div className="flex items-center gap-2">
          {/* Theme toggle */}
          <button
            onClick={toggleTheme}
            className="flex items-center justify-center w-8 h-8 text-text-muted hover:text-text rounded transition-colors focus-visible:ring-2 ring-primary"
            aria-label={theme === 'dark' ? t('theme.switch_to_light') : t('theme.switch_to_dark')}
            title={theme === 'dark' ? t('theme.switch_to_light') : t('theme.switch_to_dark')}
          >
            {theme === 'dark' ? <Sun size={15} aria-hidden="true" /> : <Moon size={15} aria-hidden="true" />}
          </button>

          {/* Language toggle */}
          <button
            onClick={toggleLang}
            className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs text-text-muted hover:text-text rounded transition-colors focus-visible:ring-2 ring-primary"
            aria-label={t('language.switch_hint')}
          >
            <Globe size={13} aria-hidden="true" />
            <span className="font-medium">{language.toUpperCase()}</span>
          </button>

          {token ? (
            <>
              <Link
                to="/dashboard"
                className="inline-flex items-center px-4 py-1.5 text-sm font-medium rounded transition-colors focus-visible:ring-2 ring-primary"
                style={{ background: 'var(--color-primary)', color: '#fff' }}
                onMouseEnter={e => (e.currentTarget.style.background = 'var(--color-primary-hover)')}
                onMouseLeave={e => (e.currentTarget.style.background = 'var(--color-primary)')}
              >
                {t('landing.nav_dashboard')}
              </Link>
              <Link
                to="/dashboard"
                title={email ?? 'Account'}
                aria-label={email ?? 'Account'}
                className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-semibold select-none focus-visible:ring-2 ring-primary"
                style={{ background: 'rgba(13,148,136,0.15)', color: 'var(--color-primary)', boxShadow: '0 0 0 1px rgba(13,148,136,0.3)' }}
              >
                {emailInitials(email)}
              </Link>
            </>
          ) : (
            <>
              <Link
                to="/auth/login"
                className="hidden sm:inline-flex items-center px-3.5 py-1.5 text-sm text-text-muted hover:text-text transition-colors rounded focus-visible:ring-2 ring-primary"
              >
                {t('landing.nav_login')}
              </Link>
              <Link
                to="/auth/register"
                className="inline-flex items-center px-4 py-1.5 text-sm font-medium rounded transition-colors focus-visible:ring-2 ring-primary"
                style={{ background: 'var(--color-primary)', color: '#fff' }}
                onMouseEnter={e => (e.currentTarget.style.background = 'var(--color-primary-hover)')}
                onMouseLeave={e => (e.currentTarget.style.background = 'var(--color-primary)')}
              >
                {t('landing.nav_get_started')}
              </Link>
            </>
          )}
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
  const { t } = useTranslation()
  const features = t('landing.hero_features', { returnObjects: true }) as string[]
  return (
    <section className="relative pt-32 pb-24 px-6 overflow-hidden">
      <div
        className="absolute end-0 top-1/2 -translate-y-1/2 w-[640px] h-[640px] pointer-events-none"
        aria-hidden="true"
        style={{ background: 'radial-gradient(circle at 70% 50%, rgba(13,148,136,0.12) 0%, transparent 70%)' }}
      />
      <div
        className="absolute start-0 bottom-0 w-[400px] h-[400px] pointer-events-none"
        aria-hidden="true"
        style={{ background: 'radial-gradient(circle at 30% 80%, rgba(13,148,136,0.06) 0%, transparent 70%)' }}
      />

      <div className="relative max-w-6xl mx-auto grid lg:grid-cols-2 gap-16 items-center">
        <div className="max-w-xl">
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
              {t('landing.hero_heading')}
            </h1>
          </FadeIn>
          <FadeIn delay={0.14}>
            <p className="text-lg text-text-muted leading-relaxed mb-8">
              {t('landing.hero_body')}
            </p>
          </FadeIn>

          <FadeIn delay={0.18}>
            <ul className="flex flex-col gap-2 mb-10" aria-label={t('landing.nav_features')}>
              {features.map((item) => (
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
                {t('landing.cta_demo')}
                <ArrowRight size={14} aria-hidden="true" className="rtl:rotate-180" />
              </Link>
              <a
                href="#how-it-works"
                onClick={(e) => scrollToId(e, 'how-it-works')}
                className="inline-flex items-center px-6 py-2.5 text-sm font-semibold rounded border border-border-subtle text-text-muted hover:text-text hover:border-text-muted transition-colors focus-visible:ring-2 ring-primary"
              >
                {t('landing.cta_how')}
              </a>
            </div>
          </FadeIn>
        </div>

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

const REG_ICONS = [Shield, FileCheck, CheckCircle2]

function RegulatoryStrip() {
  const { t } = useTranslation()
  const items = t('landing.regulatory_items', { returnObjects: true }) as Array<{ title: string; body: string }>
  return (
    <section id="frameworks" className="scroll-mt-20 py-16 px-6 border-y border-border" aria-labelledby="frameworks-heading">
      <div className="max-w-6xl mx-auto">
        <FadeIn>
          <p id="frameworks-heading" className="text-xs font-semibold uppercase tracking-widest text-text-muted mb-8">
            {t('landing.regulatory_coverage')}
          </p>
        </FadeIn>
        <div className="grid md:grid-cols-3 gap-4">
          {items.map((reg, i) => {
            const Icon = REG_ICONS[i] ?? Shield
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
                    <div className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0 mt-0.5" style={{ background: 'rgba(13,148,136,0.12)' }}>
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

// ─── How it works (redesigned: real multi-model pipeline + confidence preview) ─

const STEP_ICONS = [FileCheck, Layers, Sparkles, BarChart3]

function HowItWorks() {
  const { t } = useTranslation()
  const steps = t('landing.steps', { returnObjects: true }) as Array<{ step: string; title: string; body: string }>
  const examples = t('landing.confidence_examples', { returnObjects: true }) as Array<{ label: string; value: string; confidence: number }>

  return (
    <section id="how-it-works" className="scroll-mt-20 py-20 px-6" aria-labelledby="how-it-works-heading">
      <div className="max-w-6xl mx-auto">
        <FadeIn>
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-semibold mb-4"
            style={{ background: 'rgba(13,148,136,0.12)', border: '1px solid rgba(13,148,136,0.25)', color: 'var(--color-primary)' }}
          >
            <Sparkles size={11} aria-hidden="true" />
            {t('landing.pipeline_badge')}
          </div>
          <h2 id="how-it-works-heading" className="text-2xl font-semibold text-text mb-2">{t('landing.how_it_works_heading')}</h2>
          <p className="text-text-muted text-sm mb-12 max-w-2xl">{t('landing.how_it_works_subheading')}</p>
        </FadeIn>

        {/* Pipeline steps */}
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5 mb-12">
          {steps.map((step, i) => {
            const Icon = STEP_ICONS[i] ?? FileCheck
            return (
              <FadeIn key={step.step} delay={i * 0.08}>
                <div
                  className="relative rounded-xl p-5 h-full flex flex-col gap-3 transition-all hover:-translate-y-1"
                  style={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)' }}
                >
                  <div className="flex items-center justify-between">
                    <div
                      className="w-9 h-9 rounded-lg flex items-center justify-center"
                      style={{ background: 'rgba(13,148,136,0.1)' }}
                    >
                      <Icon size={17} style={{ color: 'var(--color-primary)' }} aria-hidden="true" />
                    </div>
                    <span
                      className="text-xs font-bold"
                      style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-primary)', opacity: 0.5 }}
                      aria-hidden="true"
                    >
                      {step.step}
                    </span>
                  </div>
                  <p className="font-semibold text-text text-sm leading-snug">{step.title}</p>
                  <p className="text-text-muted text-xs leading-relaxed">{step.body}</p>
                  {/* Desktop connector arrow */}
                  {i < steps.length - 1 && (
                    <div className="hidden lg:block absolute top-1/2 -end-3 -translate-y-1/2 text-border z-10" aria-hidden="true">
                      <ArrowRight size={14} className="rtl:rotate-180" style={{ color: 'var(--color-primary)', opacity: 0.4 }} />
                    </div>
                  )}
                </div>
              </FadeIn>
            )
          })}
        </div>

        {/* Confidence preview — shows the per-metric confidence as a percentage */}
        <FadeIn delay={0.1}>
          <div
            className="rounded-2xl p-6 sm:p-8 grid md:grid-cols-2 gap-8 items-center"
            style={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)' }}
          >
            <div>
              <h3 className="font-semibold text-text text-lg mb-2">{t('landing.confidence_preview_title')}</h3>
              <p className="text-text-muted text-sm leading-relaxed">{t('landing.confidence_preview_note')}</p>
            </div>
            <div className="flex flex-col gap-3.5">
              {examples.map((ex, i) => (
                <div key={i} className="flex flex-col gap-1.5">
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="text-sm text-text font-medium truncate">{ex.label}</span>
                    <span className="text-xs text-text-muted shrink-0" style={{ fontFamily: 'var(--font-mono)' }}>{ex.value}</span>
                  </div>
                  <div className="flex items-center gap-2.5">
                    <div className="flex-1 h-1.5 rounded-full overflow-hidden" style={{ background: 'var(--color-border)' }}>
                      <motion.div
                        className="h-full rounded-full"
                        style={{ background: confidenceColor(ex.confidence) }}
                        initial={{ width: 0 }}
                        whileInView={{ width: `${ex.confidence}%` }}
                        viewport={{ once: true }}
                        transition={{ duration: 0.8, delay: i * 0.1, ease: 'easeOut' }}
                      />
                    </div>
                    <span
                      className="text-xs font-bold tabular-nums shrink-0 w-9 text-end"
                      style={{ color: confidenceColor(ex.confidence) }}
                    >
                      {ex.confidence}%
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </FadeIn>
      </div>
    </section>
  )
}

// ─── Key metrics / stats ──────────────────────────────────────────────────────

function Stats() {
  const { t } = useTranslation()
  const stats = t('landing.stats', { returnObjects: true }) as Array<{ value: string; label: string }>
  return (
    <section className="py-16 px-6" style={{ background: 'var(--color-surface)' }} aria-label="Platform statistics">
      <div className="max-w-6xl mx-auto grid sm:grid-cols-2 lg:grid-cols-4 gap-px" style={{ background: 'var(--color-border)' }}>
        {stats.map((stat, i) => (
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

interface Plan {
  name: string
  price: string
  period: string
  description: string
  cta: string
  features: string[]
}

function CheckIcon({ highlight }: { highlight: boolean }) {
  return (
    <svg width={14} height={14} viewBox="0 0 14 14" fill="none" className="mt-0.5 shrink-0" aria-hidden="true">
      <circle cx="7" cy="7" r="7" fill={highlight ? 'rgba(255,255,255,0.2)' : 'rgba(13,148,136,0.15)'} />
      <path d="M4 7l2 2 4-4" stroke={highlight ? '#fff' : 'var(--color-primary)'} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function Pricing() {
  const { t } = useTranslation()
  const plans = t('landing.plans', { returnObjects: true }) as Plan[]
  const contactCTA = useContactCTA()

  return (
    <section id="pricing" className="scroll-mt-20 py-24 px-6" aria-labelledby="pricing-heading">
      <div className="max-w-6xl mx-auto">
        <FadeIn>
          <h2 id="pricing-heading" className="text-2xl font-semibold text-text mb-2">{t('landing.pricing_heading')}</h2>
          <p className="text-text-muted text-sm mb-14 max-w-lg">{t('landing.pricing_subheading')}</p>
        </FadeIn>

        <div className="grid md:grid-cols-3 gap-6 items-start">
          {plans.map((plan, i) => {
            const highlight = i === 1
            const isConsultant = i === 2
            const ctaClass = 'mt-2 w-full py-2.5 text-sm font-semibold rounded text-center transition-colors block focus-visible:ring-2 ring-primary ring-offset-1'
            const ctaStyle = highlight
              ? { background: '#fff', color: 'var(--color-primary)' }
              : { background: 'var(--color-surface-raised)', color: 'var(--color-text)' }
            return (
              <FadeIn key={plan.name} delay={i * 0.08}>
                <div
                  className="rounded-xl p-7 flex flex-col gap-6 h-full relative transition-transform duration-200 hover:-translate-y-1"
                  style={{
                    background: highlight ? 'var(--color-primary)' : 'var(--color-surface)',
                    border: highlight ? '1.5px solid var(--color-primary)' : '1px solid var(--color-border)',
                    boxShadow: highlight ? '0 8px 32px rgba(13,148,136,0.25)' : undefined,
                  }}
                >
                  {highlight && (
                    <div
                      className="absolute -top-3 start-1/2 -translate-x-1/2 px-3 py-0.5 rounded-full text-xs font-bold tracking-wide"
                      style={{ background: '#fff', color: 'var(--color-primary)' }}
                    >
                      {t('landing.most_popular')}
                    </div>
                  )}

                  <div>
                    <p className="text-xs font-bold uppercase tracking-widest mb-2" style={{ color: highlight ? 'rgba(255,255,255,0.75)' : 'var(--color-primary)' }}>
                      {plan.name}
                    </p>
                    <p className="text-sm leading-snug" style={{ color: highlight ? 'rgba(255,255,255,0.8)' : 'var(--color-text-muted)' }}>
                      {plan.description}
                    </p>
                  </div>

                  <div>
                    <span className="text-3xl font-semibold" style={{ fontFamily: 'var(--font-mono)', color: highlight ? '#fff' : 'var(--color-text)' }}>
                      {plan.price}
                    </span>
                    <span className="text-sm ms-1" style={{ color: highlight ? 'rgba(255,255,255,0.65)' : 'var(--color-text-muted)' }}>
                      {plan.period}
                    </span>
                  </div>

                  <ul className="flex flex-col gap-2.5 flex-1" aria-label={`${plan.name} features`}>
                    {plan.features.map((f) => (
                      <li key={f} className="flex items-start gap-2.5 text-sm">
                        <CheckIcon highlight={highlight} />
                        <span style={{ color: highlight ? 'rgba(255,255,255,0.9)' : 'var(--color-text-muted)' }}>{f}</span>
                      </li>
                    ))}
                  </ul>

                  {/* CTA — Consultant routes through register → contact; others go to register */}
                  {isConsultant ? (
                    <button type="button" onClick={contactCTA} className={ctaClass} style={ctaStyle}>
                      {plan.cta}
                    </button>
                  ) : (
                    <Link to="/auth/register" className={ctaClass} style={ctaStyle}>
                      {plan.cta}
                    </Link>
                  )}
                </div>
              </FadeIn>
            )
          })}
        </div>

        <FadeIn delay={0.25}>
          <p className="mt-10 text-center text-xs text-text-subtle">
            {t('landing.vat_note')} {t('landing.enterprise_note')}{' '}
            <a href="#contact" onClick={(e) => scrollToId(e, 'contact')} className="underline hover:text-text-muted transition-colors">
              {t('landing.contact_us_link')}
            </a>.
          </p>
        </FadeIn>
      </div>
    </section>
  )
}

// ─── Contact ──────────────────────────────────────────────────────────────────

function Contact() {
  const { t } = useTranslation()
  const email = t('landing.contact_email')
  const fields = [
    { label: t('landing.contact_name_label'), type: 'text', placeholder: t('landing.contact_name_placeholder'), autoComplete: 'name' },
    { label: t('landing.contact_institution_label'), type: 'text', placeholder: t('landing.contact_institution_placeholder'), autoComplete: 'organization' },
    { label: t('landing.contact_email_label'), type: 'email', placeholder: t('landing.contact_email_placeholder'), autoComplete: 'email' },
  ]
  return (
    <section
      id="contact"
      className="scroll-mt-20 py-20 px-6"
      style={{ background: 'var(--color-surface)', borderTop: '1px solid var(--color-border)' }}
      aria-labelledby="contact-heading"
    >
      <div className="max-w-6xl mx-auto grid md:grid-cols-2 gap-12 items-center">
        <FadeIn>
          <h2 id="contact-heading" className="text-2xl font-semibold text-text mb-3">{t('landing.contact_heading')}</h2>
          <p className="text-text-muted text-sm leading-relaxed mb-6">{t('landing.contact_body')}</p>
          <div className="flex flex-col gap-3 text-sm text-text-muted">
            <span className="flex items-center gap-2">
              <span aria-hidden="true">📍</span>
              {t('landing.contact_location')}
            </span>
            <a href={`mailto:${email}`} className="flex items-center gap-2 hover:text-text transition-colors w-fit">
              <span aria-hidden="true">✉️</span>
              {email}
            </a>
            <span className="flex items-center gap-2">
              <span aria-hidden="true">🌐</span>
              {t('landing.contact_languages')}
            </span>
          </div>
        </FadeIn>
        <FadeIn delay={0.1}>
          <div className="rounded-xl p-7" style={{ background: 'var(--color-bg)', border: '1px solid var(--color-border)' }}>
            <div className="flex flex-col gap-4">
              {fields.map((field) => (
                <div key={field.label} className="flex flex-col gap-1.5">
                  <label className="text-xs font-semibold text-text-muted" htmlFor={`contact-${field.autoComplete}`}>
                    {field.label}
                  </label>
                  <input
                    id={`contact-${field.autoComplete}`}
                    type={field.type}
                    placeholder={field.placeholder}
                    autoComplete={field.autoComplete}
                    className="w-full px-3 py-2 text-sm rounded outline-none transition-all focus-visible:ring-2 ring-primary"
                    style={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)', color: 'var(--color-text)' }}
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
                onClick={() => alert(t('landing.contact_submitted'))}
              >
                {t('landing.contact_submit')}
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
  const { t } = useTranslation()
  const contactCTA = useContactCTA()
  return (
    <section className="py-24 px-6 text-center">
      <FadeIn>
        <div
          className="w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-6"
          style={{ background: 'rgba(13,148,136,0.1)', border: '1px solid rgba(13,148,136,0.2)' }}
          aria-hidden="true"
        >
          <Zap size={24} style={{ color: 'var(--color-primary)' }} />
        </div>
        <h2 className="text-2xl font-semibold text-text mb-4">{t('landing.bottom_cta_heading')}</h2>
        <p className="text-text-muted text-sm mb-8 max-w-md mx-auto">{t('landing.bottom_cta_body')}</p>
        <div className="flex flex-wrap items-center justify-center gap-4">
          <Link
            to="/auth/register"
            className="inline-flex items-center gap-2 px-8 py-3 text-sm font-semibold rounded transition-colors focus-visible:ring-2 ring-primary ring-offset-2"
            style={{ background: 'var(--color-primary)', color: '#fff' }}
            onMouseEnter={e => (e.currentTarget.style.background = 'var(--color-primary-hover)')}
            onMouseLeave={e => (e.currentTarget.style.background = 'var(--color-primary)')}
          >
            {t('landing.bottom_cta_button')}
            <ArrowRight size={14} aria-hidden="true" className="rtl:rotate-180" />
          </Link>
          <button
            type="button"
            onClick={contactCTA}
            className="text-sm text-text-muted hover:text-text transition-colors underline underline-offset-4 focus-visible:ring-2 ring-primary rounded"
          >
            {t('landing.talk_to_expert')}
          </button>
        </div>
      </FadeIn>
    </section>
  )
}

// ─── Footer ───────────────────────────────────────────────────────────────────

function Footer() {
  const { t } = useTranslation()
  const links = [
    { id: 'frameworks', label: t('landing.footer_frameworks') },
    { id: 'pricing', label: t('landing.footer_pricing') },
    { id: 'contact', label: t('landing.footer_contact') },
  ]
  return (
    <footer className="py-8 px-6 border-t" style={{ borderColor: 'var(--color-border)' }}>
      <div className="max-w-6xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-text-subtle">
        <span>{t('landing.footer_copyright')}</span>
        <div className="flex items-center gap-4">
          {links.map((link) => (
            <a
              key={link.id}
              href={`#${link.id}`}
              onClick={(e) => scrollToId(e, link.id)}
              className="hover:text-text-muted transition-colors"
            >
              {link.label}
            </a>
          ))}
        </div>
      </div>
    </footer>
  )
}

// ─── Page export ──────────────────────────────────────────────────────────────

export default function Landing() {
  // Scroll to the hash target on mount (e.g. after register → "/#contact").
  useEffect(() => {
    if (window.location.hash) {
      const id = window.location.hash.slice(1)
      const t = setTimeout(() => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 120)
      return () => clearTimeout(t)
    }
  }, [])

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
