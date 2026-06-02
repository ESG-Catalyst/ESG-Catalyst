import { useId, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Eye, EyeOff, Loader2, LogIn } from 'lucide-react'
import { motion } from 'framer-motion'
import AuthPanel from '@/components/layout/AuthPanel'
import { login } from '@/api/auth'
import { useAuthStore } from '@/store/auth'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'

const schema = z.object({
  email: z.string().email('Enter a valid email address'),
  password: z.string().min(1, 'Password is required'),
  remember: z.boolean().optional(),
})

type FormValues = z.infer<typeof schema>

export default function Login() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const setAuth = useAuthStore((s) => s.setAuth)
  const [serverError, setServerError] = useState<string | null>(null)
  const [showPassword, setShowPassword] = useState(false)

  const emailId = useId()
  const passwordId = useId()
  const rememberId = useId()

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) })

  async function onSubmit(values: FormValues) {
    setServerError(null)
    try {
      const res = await login({ email: values.email, password: values.password })
      setAuth(res.access_token, res.user_id, res.role, values.email)
      navigate('/dashboard', { replace: true })
    } catch (err: unknown) {
      const msg = extractErrorMessage(err)
      setServerError(msg)
    }
  }

  return (
    <div className="min-h-screen grid lg:grid-cols-[60%_40%] bg-bg">
      <AuthPanel />

      {/* Right — form panel */}
      <div className="flex flex-col justify-center px-8 py-12 max-w-md w-full mx-auto lg:mx-0 lg:px-12">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, ease: 'easeOut' }}
        >
          {/* Heading */}
          <div className="mb-8">
            <div className="flex items-center gap-2 mb-3">
              <div
                className="w-8 h-8 rounded-lg flex items-center justify-center"
                style={{ background: 'var(--color-primary)' }}
              >
                <LogIn size={15} color="#fff" />
              </div>
              <span className="text-xs font-semibold uppercase tracking-widest text-text-muted">
                ESG Catalyst
              </span>
            </div>
            <h1 className="text-2xl font-semibold text-text leading-tight">
              {t('auth.login')}
            </h1>
            <p className="text-sm text-text-muted mt-1.5">
              {t('auth.no_account')}{' '}
              <Link
                to="/auth/register"
                className="text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary rounded"
              >
                {t('auth.submit_register')}
              </Link>
            </p>
          </div>

          {/* Server error banner */}
          {serverError && (
            <motion.div
              initial={{ opacity: 0, scale: 0.97 }}
              animate={{ opacity: 1, scale: 1 }}
              className="mb-5 flex items-start gap-2.5 px-4 py-3 rounded-lg text-sm text-danger border border-danger/30 bg-danger/8"
              role="alert"
            >
              <span className="mt-0.5 shrink-0 text-danger" aria-hidden="true">⚠</span>
              {serverError}
            </motion.div>
          )}

          <form onSubmit={handleSubmit(onSubmit)} noValidate className="flex flex-col gap-5">
            {/* Email */}
            <Field id={emailId} label={t('auth.email')} error={errors.email?.message}>
              <input
                id={emailId}
                type="email"
                autoComplete="email"
                {...register('email')}
                className={inputCls(!!errors.email)}
                placeholder="you@institution.eg"
                aria-invalid={!!errors.email}
                aria-describedby={errors.email ? `${emailId}-err` : undefined}
              />
            </Field>

            {/* Password */}
            <Field id={passwordId} label={t('auth.password')} error={errors.password?.message}>
              <div className="relative">
                <input
                  id={passwordId}
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="current-password"
                  {...register('password')}
                  className={cn(inputCls(!!errors.password), 'pe-10')}
                  placeholder="••••••••"
                  aria-invalid={!!errors.password}
                  aria-describedby={errors.password ? `${passwordId}-err` : undefined}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                  className="absolute inset-y-0 end-0 flex items-center pe-3 text-text-subtle hover:text-text-muted transition-colors"
                  tabIndex={-1}
                >
                  {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
                </button>
              </div>
            </Field>

            {/* Remember + Forgot row */}
            <div className="flex items-center justify-between text-sm">
              <label
                htmlFor={rememberId}
                className="flex items-center gap-2 text-text-muted cursor-pointer select-none"
              >
                <input
                  id={rememberId}
                  type="checkbox"
                  {...register('remember')}
                  className="w-3.5 h-3.5 rounded accent-primary focus-visible:ring-2 focus-visible:ring-primary"
                />
                <span className="text-xs">Remember me</span>
              </label>
              <a
                href="#"
                className="text-xs text-text-muted hover:text-text transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary rounded"
              >
                Forgot password?
              </a>
            </div>

            {/* Submit */}
            <button
              type="submit"
              disabled={isSubmitting}
              className="mt-1 flex items-center justify-center gap-2 w-full py-2.5 text-sm font-semibold rounded-lg transition-all disabled:opacity-60 disabled:cursor-not-allowed bg-primary hover:bg-primary-hover text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2"
            >
              {isSubmitting ? (
                <Loader2 size={15} className="animate-spin" aria-hidden="true" />
              ) : (
                <LogIn size={15} aria-hidden="true" />
              )}
              {isSubmitting ? 'Signing in…' : t('auth.submit_login')}
            </button>
          </form>

          {/* Footer note */}
          <p className="mt-8 text-center text-xs text-text-subtle">
            By signing in you agree to the{' '}
            <a href="#" className="hover:underline text-text-muted">Terms of Service</a>
            {' '}and{' '}
            <a href="#" className="hover:underline text-text-muted">Privacy Policy</a>.
          </p>
        </motion.div>
      </div>
    </div>
  )
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function inputCls(hasError: boolean) {
  return cn(
    'w-full px-3 py-2.5 text-sm rounded-lg outline-none transition-colors',
    'bg-surface-raised text-text placeholder:text-text-subtle',
    'border',
    'focus-visible:ring-2 focus-visible:ring-primary focus-visible:border-primary',
    hasError
      ? 'border-danger focus-visible:ring-danger focus-visible:border-danger'
      : 'border-border-subtle hover:border-border',
  )
}

function Field({
  id,
  label,
  error,
  children,
}: {
  id: string
  label: string
  error?: string
  children: React.ReactNode
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-xs font-medium text-text-muted">
        {label}
      </label>
      {children}
      {error && (
        <p id={`${id}-err`} className="text-xs text-danger flex items-center gap-1" role="alert">
          <span aria-hidden="true">·</span>
          {error}
        </p>
      )}
    </div>
  )
}

function extractErrorMessage(err: unknown): string {
  if (err && typeof err === 'object' && 'response' in err) {
    const response = (err as { response?: { data?: { detail?: string } } }).response
    if (response?.data?.detail) return response.data.detail
  }
  return 'Login failed. Check your credentials and try again.'
}
