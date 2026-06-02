import { useEffect } from 'react'
import { RouterProvider } from 'react-router-dom'
import { QueryClientProvider } from '@tanstack/react-query'
import { router } from './router'
import { queryClient } from './lib/queryClient'
import { ErrorBoundary } from './components/ErrorBoundary'
import { useUIStore, applyLang } from './store/ui'

/**
 * Sync document dir/lang whenever the language preference in the store changes.
 * The store's module-level initialiser handles the very first paint (no FOUC),
 * and this effect keeps it in sync for in-session toggles.
 */
function DirLangSync() {
  const language = useUIStore((s) => s.language)
  useEffect(() => {
    applyLang(language)
  }, [language])
  return null
}

export default function App() {
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <DirLangSync />
        <RouterProvider router={router} />
      </QueryClientProvider>
    </ErrorBoundary>
  )
}
