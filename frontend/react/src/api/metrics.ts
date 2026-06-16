import apiClient from './client'

export interface MetricDTO {
  id: string
  gri_code: string
  fra_code?: string | null
  sasb_code?: string | null
  label: string
  value?: number | null
  unit?: string | null
  original_value?: string | null
  confidence: number
  status: string
  source_file?: string | null
  source_page?: number | null
  evidence_chunk?: string | null
  pillar?: string | null
  topic?: string | null
  // Framework the indicator belongs to (GRI | SASB-FN-* | FRA). Backend
  // ExtractedMetricSchema serializes this; the GRI Content Index "Required"
  // column on ReportView keys off it (FRA disclosures are mandatory).
  framework?: string | null
}

export interface UpdateMetricRequest {
  status?: string
  value?: number | null
  unit?: string | null
  note?: string | null
}

export async function getMetrics(documentId: string): Promise<MetricDTO[]> {
  const res = await apiClient.get<MetricDTO[]>(`/api/v1/metrics/${documentId}`)
  return res.data
}

export async function updateMetric(
  metricId: string,
  data: UpdateMetricRequest,
): Promise<MetricDTO> {
  const res = await apiClient.patch<MetricDTO>(`/api/v1/metrics/${metricId}`, data)
  return res.data
}
