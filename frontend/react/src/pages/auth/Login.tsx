import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Loader2 } from 'lucide-react'
import AuthPanel from '@/components/layout/AuthPanel'
import { login } from '@/api/auth'
import { useAuthStore } from '@/store/auth'
import { useTranslation } from 'react-i18next'

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
    <div className="min-h-screen grid lg:grid-cols-[60%_40%]" style={{ background: 'var(--color-bg)' }}>
      <AuthPanel />

      {/* Right — form */}
      <div className="flex flex-col justify-center px-8 py-12 max-w-md w-full mx-auto lg:mx-0 lg:px-12">
        <div className="mb-8">
          <h1 className="text-2xl font-semibold text-text mb-1">{t('auth.login')}</h1>
          <p className="text-sm text-text-muted">
            Don't have an account?{' '}
            <Link to="/auth/register" className="text-primary hover:underline">
              {t('auth.submit_register')}
            </Link>
          </p>
        </div>

        {serverError && (
          <div className="mb-5 px-4 py-3 rounded text-sm text-danger border border-danger/30 bg-danger/10">
            {serverError}
          </div>
        )}

        <form onSubmit={handleSubmit(onSubmit)} noValidate className="flex flex-col gap-5">
          {/* Email */}
          <Field label={t('auth.email')} error={errors.email?.message}>
            <input
              type="email"
              autoComplete="email"
              {...register('email')}
              className={inputCls(!!errors.email)}
              placeholder="you@institution.eg"
            />
          </Field>

          {/* Password */}
          <Field label={t('auth.password')} error={errors.password?.message}>
            <input
              type="password"
              autoComplete="current-password"
              {...register('password')}
              className={inputCls(!!errors.password)}
              placeholder="••••••••"
            />
          </Field>

          {/* Remember + Forgot */}
          <div className="flex items-center justify-between text-sm">
            <label className="flex items-center gap-2 text-text-muted cursor-pointer select-none">
              <input
                type="checkbox"
                {...register('remember')}
                className="w-3.5 h-3.5 rounded accent-primary"
              />
              Remember me
            </label>
            <a href="#" className="text-text-muted hover:text-text transition-colors">
              Forgot password?
            </a>
          </div>

          {/* Submit */}
          <button
            type="submit"
            disabled={isSubmitting}
            className="mt-1 flex items-center justify-center gap-2 w-full py-2.5 text-sm font-semibold rounded transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
            style={{ background: 'var(--color-primary)', color: '#fff' }}
            onMouseEnter={e => { if (!isSubmitting) e.currentTarget.style.background = 'var(--color-primary-hover)' }}
            onMouseLeave={e => { e.currentTarget.style.background = 'var(--color-primary)' }}
          >
            {isSubmitting && <Loader2 size={15} className="animate-spin" />}
            {t('auth.submit_login')}
          </button>
        </form>
      </div>
    </div>
  )
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function inputCls(hasError: boolean) {
  return [
    'w-full px-3 py-2 text-sm rounded outline-none transition-colors',
    'bg-surface-raised text-text placeholder:text-text-subtle',
    'border',
    hasError
      ? 'border-danger focus:border-danger'
      : 'border-border-subtle focus:border-primary',
  ].join(' ')
}

function Field({
  label,
  error,
  children,
}: {
  label: string
  error?: string
  children: React.ReactNode
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label className="text-xs font-medium text-text-muted">{label}</label>
      {children}
      {error && <p className="text-xs text-danger">{error}</p>}
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
