import apiClient from './client'

export interface PipelineRunRequest {
  document_ids: string[]
}

export interface PipelineJob {
  job_id: string
  document_id: string
  document_ids?: string[]
  report_id?: string
}

export interface PipelineStatus {
  job_id: string
  stage: string
  progress: number
  error: string | null
}

export async function runPipeline(data: PipelineRunRequest): Promise<PipelineJob> {
  const res = await apiClient.post<PipelineJob>('/api/v1/pipeline/run', data)
  return res.data
}

export async function getPipelineStatus(jobId: string): Promise<PipelineStatus> {
  const res = await apiClient.get<PipelineStatus>(`/api/v1/pipeline/status/${jobId}`)
  return res.data
}
