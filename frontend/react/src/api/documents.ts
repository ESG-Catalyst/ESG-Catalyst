import apiClient from './client'

// Shape returned by backend DocumentSchema
interface _BackendDocument {
  id: string
  company_id: string
  report_id: string | null
  filename: string
  file_type: string
  status: string
  page_count: number | null
  language: string | null
  uploaded_by: string | null
  created_at: string
  updated_at: string
}

// Shape consumed by frontend pages (kept stable so callers don't change)
export interface DocumentRecord {
  document_id: string
  filename: string
  status: string
  company_id: string
  uploaded_at: string
  report_id: string | null
  page_count: number | null
  language: string | null
}

function toRecord(d: _BackendDocument): DocumentRecord {
  return {
    document_id: d.id,
    filename: d.filename,
    status: d.status,
    company_id: d.company_id,
    uploaded_at: d.created_at,
    report_id: d.report_id,
    page_count: d.page_count,
    language: d.language,
  }
}

export interface DocumentUploadResponse {
  document_id: string
  filename: string
  status: string
}

export async function uploadDocument(file: File, companyId?: string): Promise<DocumentUploadResponse> {
  const form = new FormData()
  form.append('file', file)
  if (companyId) form.append('company_id', companyId)

  const res = await apiClient.post<{ document_id: string; filename: string; status: string }>(
    '/api/v1/documents/upload',
    form,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  )
  return res.data
}

export async function getDocument(documentId: string): Promise<DocumentRecord> {
  const res = await apiClient.get<_BackendDocument>(`/api/v1/documents/${documentId}`)
  return toRecord(res.data)
}

export async function listDocuments(): Promise<DocumentRecord[]> {
  const res = await apiClient.get<_BackendDocument[]>('/api/v1/documents/')
  return res.data.map(toRecord)
}