import apiClient from './client'

export interface GenerateReportRequest {
  document_id: string
}

export interface ReportJob {
  report_id: string
  job_id: string
  status: string
}

export interface ReportDTO {
  id: string
  company_id: string
  title: string
  reporting_year: number
  status: string
  frameworks: string[]
  total_score: number | null
  gri_score: number | null
  fra_score: number | null
  sasb_score: number | null
  // E/S/G pillar scores (0–100). Identical to the numbers the PDF prints.
  environmental_score: number | null
  social_score: number | null
  governance_score: number | null
  pdf_path: string | null
  created_by: string | null
  created_at: string
  updated_at: string
  // Inlined by GET /reports/{id} when job_id is provided
  job_state?: string | null
}

export async function generateReport(data: GenerateReportRequest): Promise<ReportJob> {
  const res = await apiClient.post<ReportJob>('/api/v1/reports/generate', data)
  return res.data
}

export async function getReport(reportId: string, jobId?: string): Promise<ReportDTO> {
  const params = jobId ? { job_id: jobId } : {}
  const res = await apiClient.get<ReportDTO>(`/api/v1/reports/${reportId}`, { params })
  return res.data
}

export async function getReportPdf(reportId: string): Promise<Blob> {
  const res = await apiClient.get(`/api/v1/reports/${reportId}/pdf`, {
    responseType: 'blob',
  })
  return res.data as Blob
}

export async function listReports(): Promise<ReportDTO[]> {
  const res = await apiClient.get<ReportDTO[]>('/api/v1/reports/')
  return res.data
}