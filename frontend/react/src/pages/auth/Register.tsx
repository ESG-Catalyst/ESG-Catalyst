import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Loader2 } from 'lucide-react'
import AuthPanel from '@/components/layout/AuthPanel'
import { register as registerUser, type InstitutionType } from '@/api/auth'
import { useAuthStore } from '@/store/auth'
import { useTranslation } from 'react-i18next'

const schema = z
  .object({
    full_name: z.string().min(2, 'Full name is required'),
    email: z.string().email('Enter a valid email address'),
    password: z
      .string()
      .min(8, 'Password must be at least 8 characters')
      .regex(/\d/, 'Password must contain at least one number'),
    confirm_password: z.string(),
    institution_name: z.string().min(2, 'Institution name is required'),
    institution_type: z.enum([
      'commercial_bank',
      'investment_bank',
      'insurance',
      'leasing',
      'microfinance',
      'other',
    ] as const),
    agree_terms: z.literal(true, {
      errorMap: () => ({ message: 'You must accept the terms to continue' }),
    }),
  })
  .refine((d) => d.password === d.confirm_password, {
    path: ['confirm_password'],
    message: 'Passwords do not match',
  })

type FormValues = z.infer<typeof schema>

const INSTITUTION_OPTIONS: { value: InstitutionType; label: string }[] = [
  { value: 'commercial_bank', label: 'Commercial Bank' },
  { value: 'investment_bank', label: 'Investment Bank' },
  { value: 'insurance', label: 'Insurance Company' },
  { value: 'leasing', label: 'Leasing Company' },
  { value: 'microfinance', label: 'Microfinance Institution' },
  { value: 'other', label: 'Other' },
]

export default function Register() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const setAuth = useAuthStore((s) => s.setAuth)
  const [serverError, setServerError] = useState<string | null>(null)

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { institution_type: 'commercial_bank' },
  })

  async function onSubmit(values: FormValues) {
    setServerError(null)
    try {
      const res = await registerUser({
        full_name: values.full_name,
        email: values.email,
        password: values.password,
        institution_name: values.institution_name,
        institution_type: values.institution_type,
      })
      setAuth(res.access_token, res.user_id, res.role, values.email)
      navigate('/dashboard', { replace: true })
    } catch (err: unknown) {
      setServerError(extractErrorMessage(err))
    }
  }

  return (
    <div className="min-h-screen grid lg:grid-cols-[60%_40%]" style={{ background: 'var(--color-bg)' }}>
      <AuthPanel />

      {/* Right — form */}
      <div className="flex flex-col justify-center px-8 py-12 overflow-y-auto">
        <div className="max-w-md w-full mx-auto lg:mx-0 lg:px-2">
          <div className="mb-7">
            <h1 className="text-2xl font-semibold text-text mb-1">{t('auth.register')}</h1>
            <p className="text-sm text-text-muted">
              {t('auth.already_have_account')}{' '}
              <Link to="/auth/login" className="text-primary hover:underline">
                {t('auth.submit_login')}
              </Link>
            </p>
          </div>

          {serverError && (
            <div className="mb-5 px-4 py-3 rounded text-sm text-danger border border-danger/30 bg-danger/10">
              {serverError}
            </div>
          )}

          <form onSubmit={handleSubmit(onSubmit)} noValidate className="flex flex-col gap-4">
            {/* Full name */}
            <Field label={t('auth.fullName')} error={errors.full_name?.message}>
              <input
                type="text"
                autoComplete="name"
                {...register('full_name')}
                className={inputCls(!!errors.full_name)}
                placeholder="Ahmed Youssef"
              />
            </Field>

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
                autoComplete="new-password"
                {...register('password')}
                className={inputCls(!!errors.password)}
                placeholder="Min. 8 characters, 1 number"
              />
            </Field>

            {/* Confirm password */}
            <Field label="Confirm password" error={errors.confirm_password?.message}>
              <input
                type="password"
                autoComplete="new-password"
                {...register('confirm_password')}
                className={inputCls(!!errors.confirm_password)}
                placeholder="••••••••"
              />
            </Field>

            {/* Institution name */}
            <Field label="Institution name" error={errors.institution_name?.message}>
              <input
                type="text"
                {...register('institution_name')}
                className={inputCls(!!errors.institution_name)}
                placeholder="e.g. Banque Misr"
              />
            </Field>

            {/* Institution type */}
            <Field label="Institution type" error={errors.institution_type?.message}>
              <select
                {...register('institution_type')}
                className={selectCls(!!errors.institution_type)}
              >
                {INSTITUTION_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </Field>

            {/* Terms */}
            <div className="flex flex-col gap-1">
              <label className="flex items-start gap-2.5 text-sm text-text-muted cursor-pointer select-none">
                <input
                  type="checkbox"
                  {...register('agree_terms')}
                  className="mt-0.5 w-3.5 h-3.5 rounded accent-primary shrink-0"
                />
                <span>
                  I agree to the{' '}
                  <a href="#" className="text-primary hover:underline">
                    Terms of Service
                  </a>{' '}
                  and{' '}
                  <a href="#" className="text-primary hover:underline">
                    Privacy Policy
                  </a>
                </span>
              </label>
              {errors.agree_terms && (
                <p className="text-xs text-danger ms-5">{errors.agree_terms.message}</p>
              )}
            </div>

            {/* Submit */}
            <button
              type="submit"
              disabled={isSubmitting}
              className="mt-2 flex items-center justify-center gap-2 w-full py-2.5 text-sm font-semibold rounded transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
              style={{ background: 'var(--color-primary)', color: '#fff' }}
              onMouseEnter={e => { if (!isSubmitting) e.currentTarget.style.background = 'var(--color-primary-hover)' }}
              onMouseLeave={e => { e.currentTarget.style.background = 'var(--color-primary)' }}
            >
              {isSubmitting && <Loader2 size={15} className="animate-spin" />}
              {t('auth.submit_register')}
            </button>
          </form>
        </div>
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

function selectCls(hasError: boolean) {
  return [
    'w-full px-3 py-2 text-sm rounded outline-none transition-colors',
    'bg-surface-raised text-text',
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
  return 'Registration failed. Please try again.'
}
