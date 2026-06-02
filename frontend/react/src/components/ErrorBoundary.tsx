import { Component, type ErrorInfo, type ReactNode } from 'react'
import { AlertTriangle, RefreshCw, Home } from 'lucide-react'
import { cn } from '@/lib/utils'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

/**
 * Top-level error boundary.  Catches unexpected React render errors and shows
 * a branded recovery card instead of a blank white page.
 *
 * Stack trace is printed in dev-only mode so it never leaks to production users.
 */
export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    if (import.meta.env.DEV) {
      console.error('[ErrorBoundary]', error, info.componentStack)
    }
  }

  reset = () => this.setState({ hasError: false, error: null })

  render() {
    if (!this.state.hasError) return this.props.children

    return (
      <div
        className="min-h-screen flex items-center justify-center p-6 bg-bg"
        aria-live="assertive"
        role="alert"
      >
        <div
          className={cn(
            'max-w-md w-full rounded-xl p-8',
            'flex flex-col items-center text-center gap-5',
            'bg-surface border border-border shadow-lg',
          )}
        >
          {/* Icon */}
          <div
            className="w-14 h-14 rounded-full flex items-center justify-center"
            style={{ background: 'rgba(239,68,68,0.12)' }}
            aria-hidden="true"
          >
            <AlertTriangle size={26} style={{ color: 'var(--color-danger)' }} />
          </div>

          {/* Text */}
          <div>
            <p className="text-base font-semibold text-text mb-1.5">Something went wrong</p>
            <p className="text-sm text-text-muted leading-relaxed">
              An unexpected error occurred. You can try again or return to the home page.
            </p>

            {/* Stack trace — dev only */}
            {import.meta.env.DEV && this.state.error && (
              <pre
                className={cn(
                  'mt-4 text-start text-xs rounded-lg p-3 overflow-auto max-h-40',
                  'bg-surface-raised text-danger',
                )}
                style={{ fontFamily: 'var(--font-mono)' }}
                aria-label="Error stack trace"
              >
                {this.state.error.stack ?? this.state.error.message}
              </pre>
            )}
          </div>

          {/* Actions */}
          <div className="flex gap-3">
            <button
              onClick={this.reset}
              className={cn(
                'flex items-center gap-2 px-4 py-2 text-sm font-semibold rounded-lg transition-colors',
                'bg-primary text-white hover:bg-primary-hover',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2',
              )}
              style={{ '--tw-ring-offset-color': 'var(--color-bg)' } as React.CSSProperties}
            >
              <RefreshCw size={14} aria-hidden="true" />
              Try again
            </button>

            <button
              onClick={() => window.location.assign('/')}
              className={cn(
                'flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg transition-colors',
                'bg-surface-raised text-text-muted hover:text-text hover:bg-border',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary',
              )}
            >
              <Home size={14} aria-hidden="true" />
              Go home
            </button>
          </div>
        </div>
      </div>
    )
  }
}
