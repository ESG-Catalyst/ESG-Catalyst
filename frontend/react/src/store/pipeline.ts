import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface PipelineState {
  jobId: string | null
  documentId: string | null
  documentName: string | null
  reportId: string | null
  setJob: (jobId: string, documentId: string, documentName?: string) => void
  setReportId: (id: string) => void
  clearJob: () => void
}

export const usePipelineStore = create<PipelineState>()(
  persist(
    (set) => ({
      jobId: null,
      documentId: null,
      documentName: null,
      reportId: null,
      setJob: (jobId, documentId, documentName) =>
        // Preserve an already-stored name when the caller omits it (e.g. the
        // PipelineProgress page re-persists jobId/documentId on every mount
        // without the filename) — otherwise the resume banner loses its label.
        set((s) => ({ jobId, documentId, documentName: documentName ?? s.documentName })),
      setReportId: (reportId) => set({ reportId }),
      clearJob: () => set({ jobId: null, documentId: null, documentName: null, reportId: null }),
    }),
    { name: 'esg-pipeline-ctx' },
  ),
)