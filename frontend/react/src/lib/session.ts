import type { QueryClient } from '@tanstack/react-query'
import { usePipelineStore } from '@/store/pipeline'
import { useConsultantStore } from '@/store/consultant'

/**
 * Wipe ALL per-account client state so one account never inherits another's
 * data. Call on logout AND on every successful login / register.
 *
 * Clears:
 *  - the pipeline context (documentId / documentName / reportId)
 *  - the consultant's active client
 *  - the entire react-query cache (cached metrics / documents / reports)
 *
 * Theme + language prefs (``esg-ui-prefs``) are intentionally preserved — they
 * are device preferences, not account data.
 *
 * Why this is needed: logout/login use client-side navigation (no full page
 * reload), so without an explicit clear the previous account's react-query
 * cache stays in memory and the persisted pipeline/consultant stores carry
 * over — which made a freshly-created account show the prior account's data.
 */
export function clearAccountState(queryClient: QueryClient): void {
  usePipelineStore.getState().clearJob()
  useConsultantStore.getState().clearActiveClient()
  queryClient.clear()
}
