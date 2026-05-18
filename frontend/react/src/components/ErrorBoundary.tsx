import { Component, type ErrorInfo, type ReactNode } from 'react'
import { AlertTriangle, RefreshCw } from 'lucide-react'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

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
        className="min-h-screen flex items-center justify-center p-6"
        style={{ background: 'var(--color-bg)' }}
      >
        <div
          className="max-w-md w-full rounded-xl p-8 flex flex-col items-center text-center gap-4"
          style={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)' }}
        >
          <div
            className="w-14 h-14 rounded-full flex items-center justify-center"
            style={{ background: 'rgba(239,68,68,0.1)' }}
          >
            <AlertTriangle size={26} style={{ color: '#EF4444' }} />
          </div>
          <div>
            <p className="text-base font-semibold text-text mb-1">Something went wrong</p>
            <p className="text-sm text-text-muted">
              An unexpected error occurred. Try refreshing the page.
            </p>
            {import.meta.env.DEV && this.state.error && (
              <pre
                className="mt-3 text-left text-xs rounded p-3 overflow-auto max-h-40"
                style={{
                  background: 'var(--color-surface-raised)',
                  color: '#EF4444',
                  fontFamily: 'var(--font-mono)',
                }}
              >
                {this.state.error.message}
              </pre>
            )}
          </div>
          <div className="flex gap-3">
            <button
              onClick={this.reset}
              className="flex items-center gap-2 px-4 py-2 text-sm font-semibold rounded transition-colors"
              style={{ background: 'var(--color-primary)', color: '#fff' }}
            >
              <RefreshCw size={14} />
              Try again
            </button>
            <button
              onClick={() => window.location.assign('/')}
              className="px-4 py-2 text-sm font-medium rounded transition-colors"
              style={{ background: 'var(--color-surface-raised)', color: 'var(--color-text-muted)' }}
            >
              Go home
            </button>
          </div>
        </div>
      </div>
    )
  }
}