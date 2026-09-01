export type ReconciliationStatus = 'matched' | 'mismatch' | 'missing'

export type Transaction = {
  order_id: string
  customer: string
  order_total: number
  paid_amount: number
  status: ReconciliationStatus
  difference: number
  order_date: string
}

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = typeof window !== 'undefined' ? sessionStorage.getItem('reconcile_token') : null
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { ...(init?.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }), ...(token ? { Authorization: `Bearer ${token}` } : {}), ...init?.headers },
  })
  if (!response.ok) throw new Error(`Reconcile API error: ${response.status}`)
  return response.json() as Promise<T>
}

export const api = {
  login: (email: string, password: string) => request<{ access_token: string }>('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) }),
  upload: (orders: File, transactions: File) => { const body = new FormData(); body.append('orders_file', orders); body.append('transactions_file', transactions); return request<{ reconciliation_id: string }>('/reconcile/upload', { method: 'POST', body, headers: {} }) },
  getReconciliation: (id: string) => request<{ transactions: Transaction[] }>(`/reconcile/${encodeURIComponent(id)}`),
  explain: (id: string) => request<{ explanation: string; suggested_actions: string[] }>(`/reconcile/${encodeURIComponent(id)}/explain`, { method: 'POST' }),
}
