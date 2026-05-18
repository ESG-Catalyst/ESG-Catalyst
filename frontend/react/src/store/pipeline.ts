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
        set({ jobId, documentId, documentName: documentName ?? null }),
      setReportId: (reportId) => set({ reportId }),
      clearJob: () => set({ jobId: null, documentId: null, documentName: null, reportId: null }),
    }),
    { name: 'esg-pipeline-ctx' },
  ),
)