import { useId, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Eye, EyeOff, Loader2, UserPlus, CheckCircle2 } from 'lucide-react'
import { motion } from 'framer-motion'
import AuthPanel from '@/components/layout/AuthPanel'
import { register as registerUser, type InstitutionType } from '@/api/auth'
import { useAuthStore } from '@/store/auth'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'

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

/** Password strength helper — 0..4 */
function passwordStrength(pw: string): number {
  if (!pw) return 0
  let score = 0
  if (pw.length >= 8) score++
  if (pw.length >= 12) score++
  if (/\d/.test(pw)) score++
  if (/[^a-zA-Z0-9]/.test(pw)) score++
  return score
}

const STRENGTH_LABEL = ['', 'Weak', 'Fair', 'Good', 'Strong']
const STRENGTH_COLOR = ['', '#EF4444', '#F59E0B', '#0D9488', '#10B981']

export default function Register() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const setAuth = useAuthStore((s) => s.setAuth)
  const [serverError, setServerError] = useState<string | null>(null)
  const [showPassword, setShowPassword] = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)

  const nameId = useId()
  const emailId = useId()
  const passwordId = useId()
  const confirmId = useId()
  const institutionNameId = useId()
  const institutionTypeId = useId()
  const termsId = useId()

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { institution_type: 'commercial_bank' },
  })

  const watchedPassword = watch('password', '')
  const strength = passwordStrength(watchedPassword)

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
    <div className="min-h-screen grid lg:grid-cols-[60%_40%] bg-bg">
      <AuthPanel />

      {/* Right — form panel */}
      <div className="flex flex-col justify-center px-8 py-12 overflow-y-auto">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, ease: 'easeOut' }}
          className="max-w-md w-full mx-auto lg:mx-0 lg:px-2"
        >
          {/* Heading */}
          <div className="mb-7">
            <div className="flex items-center gap-2 mb-3">
              <div
                className="w-8 h-8 rounded-lg flex items-center justify-center"
                style={{ background: 'var(--color-primary)' }}
              >
                <UserPlus size={15} color="#fff" />
              </div>
              <span className="text-xs font-semibold uppercase tracking-widest text-text-muted">
                ESG Catalyst
              </span>
            </div>
            <h1 className="text-2xl font-semibold text-text leading-tight">
              {t('auth.register')}
            </h1>
            <p className="text-sm text-text-muted mt-1.5">
              {t('auth.already_have_account')}{' '}
              <Link
                to="/auth/login"
                className="text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary rounded"
              >
                {t('auth.submit_login')}
              </Link>
            </p>
          </div>

          {/* Server error */}
          {serverError && (
            <motion.div
              initial={{ opacity: 0, scale: 0.97 }}
              animate={{ opacity: 1, scale: 1 }}
              className="mb-5 flex items-start gap-2.5 px-4 py-3 rounded-lg text-sm text-danger border border-danger/30 bg-danger/8"
              role="alert"
            >
              <span className="mt-0.5 shrink-0" aria-hidden="true">⚠</span>
              {serverError}
            </motion.div>
          )}

          <form onSubmit={handleSubmit(onSubmit)} noValidate className="flex flex-col gap-4">
            {/* Section label */}
            <SectionLabel>Account details</SectionLabel>

            {/* Full name */}
            <Field id={nameId} label={t('auth.fullName')} error={errors.full_name?.message}>
              <input
                id={nameId}
                type="text"
                autoComplete="name"
                {...register('full_name')}
                className={inputCls(!!errors.full_name)}
                placeholder="Ahmed Youssef"
                aria-invalid={!!errors.full_name}
              />
            </Field>

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
              />
            </Field>

            {/* Password */}
            <Field id={passwordId} label={t('auth.password')} error={errors.password?.message}>
              <div className="relative">
                <input
                  id={passwordId}
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="new-password"
                  {...register('password')}
                  className={cn(inputCls(!!errors.password), 'pe-10')}
                  placeholder="Min. 8 characters, 1 number"
                  aria-invalid={!!errors.password}
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
              {/* Strength meter */}
              {watchedPassword.length > 0 && (
                <div className="mt-1.5 flex items-center gap-2">
                  <div className="flex gap-1 flex-1">
                    {[1, 2, 3, 4].map((lvl) => (
                      <div
                        key={lvl}
                        className="h-1 flex-1 rounded-full transition-all duration-300"
                        style={{
                          background: strength >= lvl ? STRENGTH_COLOR[strength] : 'var(--color-border-subtle)',
                        }}
                      />
                    ))}
                  </div>
                  <span
                    className="text-xs font-medium shrink-0"
                    style={{ color: STRENGTH_COLOR[strength] }}
                  >
                    {STRENGTH_LABEL[strength]}
                  </span>
                </div>
              )}
            </Field>

            {/* Confirm password */}
            <Field
              id={confirmId}
              label="Confirm password"
              error={errors.confirm_password?.message}
            >
              <div className="relative">
                <input
                  id={confirmId}
                  type={showConfirm ? 'text' : 'password'}
                  autoComplete="new-password"
                  {...register('confirm_password')}
                  className={cn(inputCls(!!errors.confirm_password), 'pe-10')}
                  placeholder="••••••••"
                  aria-invalid={!!errors.confirm_password}
                />
                <button
                  type="button"
                  onClick={() => setShowConfirm((v) => !v)}
                  aria-label={showConfirm ? 'Hide confirm password' : 'Show confirm password'}
                  className="absolute inset-y-0 end-0 flex items-center pe-3 text-text-subtle hover:text-text-muted transition-colors"
                  tabIndex={-1}
                >
                  {showConfirm ? <EyeOff size={15} /> : <Eye size={15} />}
                </button>
              </div>
            </Field>

            {/* Divider */}
            <SectionLabel>Institution</SectionLabel>

            {/* Institution name */}
            <Field
              id={institutionNameId}
              label="Institution name"
              error={errors.institution_name?.message}
            >
              <input
                id={institutionNameId}
                type="text"
                {...register('institution_name')}
                className={inputCls(!!errors.institution_name)}
                placeholder="e.g. Banque Misr"
                aria-invalid={!!errors.institution_name}
              />
            </Field>

            {/* Institution type */}
            <Field
              id={institutionTypeId}
              label="Institution type"
              error={errors.institution_type?.message}
            >
              <select
                id={institutionTypeId}
                {...register('institution_type')}
                className={selectCls(!!errors.institution_type)}
                aria-invalid={!!errors.institution_type}
              >
                {INSTITUTION_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </Field>

            {/* Terms */}
            <div className="flex flex-col gap-1 pt-1">
              <label
                htmlFor={termsId}
                className="flex items-start gap-2.5 text-sm text-text-muted cursor-pointer select-none"
              >
                <input
                  id={termsId}
                  type="checkbox"
                  {...register('agree_terms')}
                  className="mt-0.5 w-3.5 h-3.5 rounded accent-primary shrink-0 focus-visible:ring-2 focus-visible:ring-primary"
                  aria-invalid={!!errors.agree_terms}
                />
                <span className="text-xs leading-relaxed">
                  I agree to the{' '}
                  <a
                    href="#"
                    className="text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary rounded"
                  >
                    Terms of Service
                  </a>{' '}
                  and{' '}
                  <a
                    href="#"
                    className="text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary rounded"
                  >
                    Privacy Policy
                  </a>
                </span>
              </label>
              {errors.agree_terms && (
                <p className="text-xs text-danger ms-6" role="alert">
                  {errors.agree_terms.message}
                </p>
              )}
            </div>

            {/* Submit */}
            <button
              type="submit"
              disabled={isSubmitting}
              className="mt-2 flex items-center justify-center gap-2 w-full py-2.5 text-sm font-semibold rounded-lg transition-all disabled:opacity-60 disabled:cursor-not-allowed bg-primary hover:bg-primary-hover text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2"
            >
              {isSubmitting ? (
                <Loader2 size={15} className="animate-spin" aria-hidden="true" />
              ) : (
                <CheckCircle2 size={15} aria-hidden="true" />
              )}
              {isSubmitting ? 'Creating account…' : t('auth.submit_register')}
            </button>
          </form>
        </motion.div>
      </div>
    </div>
  )
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-[10px] font-bold uppercase tracking-widest text-text-subtle pt-1 pb-0.5 border-b border-border-subtle">
      {children}
    </p>
  )
}

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

function selectCls(hasError: boolean) {
  return cn(
    'w-full px-3 py-2.5 text-sm rounded-lg outline-none transition-colors appearance-none',
    'bg-surface-raised text-text',
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
        <p className="text-xs text-danger flex items-center gap-1" role="alert">
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
  return 'Registration failed. Please try again.'
}
