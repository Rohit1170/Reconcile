// The app works with one "active" reconciliation at a time -- the most
// recent upload or demo-data load. That id is persisted in localStorage
// (per-browser, survives refresh) so the dashboard and discrepancies pages
// know which reconciliation to fetch without needing it in the URL. This
// is a deliberate simplification: the assignment doesn't call for managing
// multiple historical reconciliations in the UI.
const KEY = 'reconcile_active_reconciliation_id'

export function getActiveReconciliationId(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem(KEY)
}

export function setActiveReconciliationId(id: string) {
  localStorage.setItem(KEY, id)
}
