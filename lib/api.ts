// Thin REST client for the FastAPI backend. Every function maps 1:1 to a
// backend route -- no client-side business logic lives here. The backend
// is the source of truth for reconciliation results, financial totals,
// and AI explanations; this file only fetches and types them.

export type DiscrepancyCategory =
  | 'MATCHED'
  | 'AMOUNT_MISMATCH'
  | 'MISSING_PAYMENT'
  | 'UNKNOWN_PAYMENT'
  | 'DUPLICATE_ORDER'
  | 'DUPLICATE_PAYMENT'
  | 'CURRENCY_MISMATCH'
  | 'REFUND_CHARGE_ISSUE'
  | 'ROUNDING_DIFFERENCE'

export type Priority = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'NONE'
export type DiscrepancyStatus = 'OPEN' | 'RESOLVED'

export type User = { id: string; name: string; email: string }

export type DatasetUploadResponse = {
  reconciliation_id: string
  orders_imported: number
  payments_imported: number
}

export type ReconciliationSummary = {
  reconciliation_id: string
  total_orders: number
  total_payments: number
  total_order_value: number
  total_payment_value: number
  matched_value: number
  disputed_value: number
  money_at_risk: number
  matched_count: number
  discrepancy_count: number
  discrepancies_by_type: { category: DiscrepancyCategory; count: number; financial_impact: number }[]
  priority_breakdown: { priority: Priority; count: number }[]
  currency_breakdown: Record<string, number>
}

export type DiscrepancyListItem = {
  id: string
  order_id: string | null
  payment_id: string | null
  category: DiscrepancyCategory
  priority: Priority
  status: DiscrepancyStatus
  order_amount: number | null
  payment_amount: number | null
  difference: number | null
  currency: string | null
  reason: string
}

export type DiscrepancyListResponse = {
  items: DiscrepancyListItem[]
  total: number
  page: number
  page_size: number
}

export type DiscrepancyDetailResponse = {
  id: string
  order: Record<string, unknown> | null
  payment: Record<string, unknown> | null
  category: DiscrepancyCategory
  priority: Priority
  status: DiscrepancyStatus
  difference: number | null
  order_currency: string | null
  payment_currency: string | null
  reason: string
  financial_impact: number
}

export type AIExplanation = {
  what_happened: string
  likely_cause: string
  recommended_action: string
  is_fallback: boolean
}

export type AIAnalysisResponse = {
  selected_count: number
  total_financial_impact: number
  summary: string
  recommended_actions: string[]
  is_fallback: boolean
}

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'
const TOKEN_KEY = 'reconcile_token'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = typeof window !== 'undefined' ? sessionStorage.getItem(TOKEN_KEY) : null
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      ...(init?.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init?.headers,
    },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new ApiError(response.status, body?.detail ?? `Request failed with status ${response.status}`)
  }
  return response.json() as Promise<T>
}

function query(params: Record<string, string | number | undefined>): string {
  const usp = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '') usp.set(key, String(value))
  }
  const qs = usp.toString()
  return qs ? `?${qs}` : ''
}

export const api = {
  signup: (name: string, email: string, password: string) =>
    request<{ access_token: string }>('/auth/signup', { method: 'POST', body: JSON.stringify({ name, email, password }) }),
  login: (email: string, password: string) =>
    request<{ access_token: string }>('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) }),
  me: () => request<User>('/auth/me'),

  uploadDatasets: (ordersFile: File, paymentsFile: File) => {
    const body = new FormData()
    body.append('orders_file', ordersFile)
    body.append('payments_file', paymentsFile)
    return request<DatasetUploadResponse>('/datasets/upload', { method: 'POST', body, headers: {} })
  },
  loadDemoData: () => request<DatasetUploadResponse>('/datasets/demo', { method: 'POST' }),

  runReconciliation: (reconciliationId: string) =>
    request<{ reconciliation_id: string; discrepancies_created: number }>(
      `/reconciliation/run/${encodeURIComponent(reconciliationId)}`,
      { method: 'POST' },
    ),
  getSummary: (reconciliationId: string) =>
    request<ReconciliationSummary>(`/reconciliation/${encodeURIComponent(reconciliationId)}/summary`),
  getDiscrepancies: (
    reconciliationId: string,
    params: { search?: string; category?: string; status?: string; currency?: string; page?: number; page_size?: number },
  ) =>
    request<DiscrepancyListResponse>(
      `/reconciliation/${encodeURIComponent(reconciliationId)}/discrepancies${query(params)}`,
    ),
  getDiscrepancy: (reconciliationId: string, discrepancyId: string) =>
    request<DiscrepancyDetailResponse>(
      `/reconciliation/${encodeURIComponent(reconciliationId)}/discrepancies/${encodeURIComponent(discrepancyId)}`,
    ),

  explainDiscrepancy: (reconciliationId: string, discrepancyId: string) =>
    request<AIExplanation>(
      `/ai/explain/${encodeURIComponent(reconciliationId)}/${encodeURIComponent(discrepancyId)}`,
      { method: 'POST' },
    ),
  analyzeDiscrepancies: (reconciliationId: string, discrepancyIds: string[]) =>
    request<AIAnalysisResponse>(`/ai/analyze/${encodeURIComponent(reconciliationId)}`, {
      method: 'POST',
      body: JSON.stringify({ discrepancy_ids: discrepancyIds }),
    }),
}

export const TOKEN_STORAGE_KEY = TOKEN_KEY
