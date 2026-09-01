'use client'

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { Search, Sparkles, X } from 'lucide-react'
import {
  api,
  ApiError,
  type AIAnalysisResponse,
  type AIExplanation,
  type DiscrepancyCategory,
  type DiscrepancyDetailResponse,
  type DiscrepancyListItem,
} from '@/lib/api'
import { getActiveReconciliationId } from '@/lib/active-reconciliation'
import { EmptyState, ErrorState, LoadingState } from '@/components/state-views'

const CATEGORIES: DiscrepancyCategory[] = [
  'MATCHED',
  'AMOUNT_MISMATCH',
  'MISSING_PAYMENT',
  'UNKNOWN_PAYMENT',
  'DUPLICATE_ORDER',
  'DUPLICATE_PAYMENT',
  'CURRENCY_MISMATCH',
  'REFUND_CHARGE_ISSUE',
  'ROUNDING_DIFFERENCE',
]

const PAGE_SIZE = 20

function formatMoney(value: number | null, currency: string | null) {
  if (value === null) return '—'
  try {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: currency ?? 'USD' }).format(value)
  } catch {
    return value.toFixed(2)
  }
}

export default function DiscrepanciesPage() {
  const reconciliationId = getActiveReconciliationId()

  const [items, setItems] = useState<DiscrepancyListItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('')
  const [status, setStatus] = useState('')
  const [currency, setCurrency] = useState('')
  const [state, setState] = useState<'loading' | 'ready' | 'error' | 'no-reconciliation'>('loading')
  const [errorMessage, setErrorMessage] = useState('')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [detailId, setDetailId] = useState<string | null>(null)
  const [analyzeOpen, setAnalyzeOpen] = useState(false)

  const load = useCallback(async () => {
    if (!reconciliationId) {
      setState('no-reconciliation')
      return
    }
    setState('loading')
    try {
      const res = await api.getDiscrepancies(reconciliationId, {
        search: search || undefined,
        category: category || undefined,
        status: status || undefined,
        currency: currency || undefined,
        page,
        page_size: PAGE_SIZE,
      })
      setItems(res.items)
      setTotal(res.total)
      setState('ready')
    } catch (err) {
      setErrorMessage(err instanceof ApiError ? err.message : 'Unable to load discrepancies.')
      setState('error')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reconciliationId, search, category, status, currency, page])

  useEffect(() => {
    load()
  }, [load])

  function toggleSelected(id: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const selectedImpact = items.filter((i) => selected.has(i.id)).reduce((sum, i) => sum + (i.difference ?? i.order_amount ?? i.payment_amount ?? 0), 0)

  return (
    <>
      <header className="flex h-16 items-center justify-between border-b bg-card px-5 lg:px-8">
        <div>
          <p className="text-sm font-medium">Discrepancies</p>
          <p className="text-xs text-muted-foreground">Review and investigate flagged transactions</p>
        </div>
      </header>
      <div className="mx-auto max-w-[1440px] p-5 lg:p-8">
        {state === 'no-reconciliation' && (
          <EmptyState
            title="No reconciliation yet"
            description="Upload your files or load demo data first."
            action={
              <Link href="/upload" className="rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:opacity-90">
                Go to Upload
              </Link>
            }
          />
        )}

        {state !== 'no-reconciliation' && (
          <>
            <div className="mb-4 flex flex-wrap gap-2">
              <div className="flex items-center gap-2 rounded-md border bg-card px-3 py-2">
                <Search className="size-4 text-muted-foreground" />
                <input
                  value={search}
                  onChange={(e) => {
                    setPage(1)
                    setSearch(e.target.value)
                  }}
                  placeholder="Search order or payment ID..."
                  className="w-48 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
                />
              </div>
              <select
                value={category}
                onChange={(e) => {
                  setPage(1)
                  setCategory(e.target.value)
                }}
                className="rounded-md border bg-card px-3 py-2 text-sm"
              >
                <option value="">All categories</option>
                {CATEGORIES.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
              <select
                value={status}
                onChange={(e) => {
                  setPage(1)
                  setStatus(e.target.value)
                }}
                className="rounded-md border bg-card px-3 py-2 text-sm"
              >
                <option value="">All statuses</option>
                <option value="OPEN">Open</option>
                <option value="RESOLVED">Resolved</option>
              </select>
              <select
                value={currency}
                onChange={(e) => {
                  setPage(1)
                  setCurrency(e.target.value)
                }}
                className="rounded-md border bg-card px-3 py-2 text-sm"
              >
                <option value="">All currencies</option>
                <option value="USD">USD</option>
                <option value="EUR">EUR</option>
              </select>
            </div>

            {state === 'loading' && <LoadingState label="Loading discrepancies..." />}
            {state === 'error' && <ErrorState message={errorMessage} onRetry={load} />}
            {state === 'ready' && items.length === 0 && (
              <EmptyState title="No discrepancies found" description="Try adjusting your search or filters." />
            )}

            {state === 'ready' && items.length > 0 && (
              <div className="rounded-lg border bg-card">
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[860px] text-left text-sm">
                    <thead className="bg-muted/50 text-xs text-muted-foreground">
                      <tr>
                        <th className="w-10 px-5 py-3" />
                        {['Order', 'Payment', 'Category', 'Priority', 'Order amount', 'Payment amount', 'Difference', 'Status'].map((h) => (
                          <th key={h} className="px-3 py-3 font-medium">
                            {h}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {items.map((row) => (
                        <tr key={row.id} className="cursor-pointer border-t transition-colors hover:bg-muted/40">
                          <td className="px-5 py-3" onClick={(e) => e.stopPropagation()}>
                            <input type="checkbox" checked={selected.has(row.id)} onChange={() => toggleSelected(row.id)} />
                          </td>
                          <td className="px-3 py-3 font-medium" onClick={() => setDetailId(row.id)}>{row.order_id ?? '—'}</td>
                          <td className="px-3 py-3 text-muted-foreground" onClick={() => setDetailId(row.id)}>{row.payment_id ?? '—'}</td>
                          <td className="px-3 py-3" onClick={() => setDetailId(row.id)}>
                            <CategoryBadge category={row.category} />
                          </td>
                          <td className="px-3 py-3" onClick={() => setDetailId(row.id)}>
                            <PriorityBadge priority={row.priority} />
                          </td>
                          <td className="px-3 py-3" onClick={() => setDetailId(row.id)}>{formatMoney(row.order_amount, row.currency)}</td>
                          <td className="px-3 py-3" onClick={() => setDetailId(row.id)}>{formatMoney(row.payment_amount, row.currency)}</td>
                          <td className="px-3 py-3 font-medium" onClick={() => setDetailId(row.id)}>
                            {row.difference ? formatMoney(row.difference, row.currency) : '—'}
                          </td>
                          <td className="px-3 py-3" onClick={() => setDetailId(row.id)}>{row.status}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="flex items-center justify-between border-t px-5 py-3 text-xs text-muted-foreground">
                  <span>
                    Showing {(page - 1) * PAGE_SIZE + 1}-{Math.min(page * PAGE_SIZE, total)} of {total}
                  </span>
                  <div className="flex gap-1">
                    <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page <= 1} className="rounded border px-2 py-1 disabled:opacity-50">
                      Previous
                    </button>
                    <button onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page >= totalPages} className="rounded border px-2 py-1 disabled:opacity-50">
                      Next
                    </button>
                  </div>
                </div>
              </div>
            )}
          </>
        )}
      </div>

      {selected.size > 0 && reconciliationId && (
        <div className="fixed inset-x-0 bottom-0 z-30 flex items-center justify-between gap-4 border-t bg-primary p-4 text-primary-foreground lg:left-64">
          <div className="flex items-center gap-4 text-sm">
            <span className="font-medium">{selected.size} selected</span>
            <span className="text-primary-foreground/75">Total impact: {formatMoney(selectedImpact, 'USD')}</span>
          </div>
          <button
            onClick={() => setAnalyzeOpen(true)}
            className="flex items-center gap-2 rounded-md bg-card px-3 py-2 text-sm font-medium text-foreground hover:bg-background"
          >
            <Sparkles className="size-4" />
            Analyze Selected
          </button>
        </div>
      )}

      {detailId && reconciliationId && (
        <DiscrepancyDrawer reconciliationId={reconciliationId} discrepancyId={detailId} onClose={() => setDetailId(null)} />
      )}

      {analyzeOpen && reconciliationId && (
        <AnalyzeModal reconciliationId={reconciliationId} discrepancyIds={[...selected]} onClose={() => setAnalyzeOpen(false)} />
      )}
    </>
  )
}

function CategoryBadge({ category }: { category: DiscrepancyCategory }) {
  const good = category === 'MATCHED'
  return (
    <span className={`inline-flex whitespace-nowrap rounded-full px-2 py-1 text-xs font-medium ${good ? 'bg-primary/10 text-primary' : 'bg-destructive/10 text-destructive'}`}>
      {category.replace(/_/g, ' ')}
    </span>
  )
}

function PriorityBadge({ priority }: { priority: string }) {
  const styles: Record<string, string> = {
    CRITICAL: 'bg-destructive/15 text-destructive',
    HIGH: 'bg-destructive/10 text-destructive',
    MEDIUM: 'bg-warning-foreground/15 text-warning-foreground',
    LOW: 'bg-muted text-muted-foreground',
    NONE: 'bg-muted text-muted-foreground',
  }
  return <span className={`inline-flex rounded-full px-2 py-1 text-xs font-medium ${styles[priority] ?? styles.NONE}`}>{priority}</span>
}

function DiscrepancyDrawer({ reconciliationId, discrepancyId, onClose }: { reconciliationId: string; discrepancyId: string; onClose: () => void }) {
  const [detail, setDetail] = useState<DiscrepancyDetailResponse | null>(null)
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading')
  const [ai, setAi] = useState<AIExplanation | null>(null)
  const [aiState, setAiState] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle')

  useEffect(() => {
    setState('loading')
    api
      .getDiscrepancy(reconciliationId, discrepancyId)
      .then((d) => {
        setDetail(d)
        setState('ready')
      })
      .catch(() => setState('error'))
  }, [reconciliationId, discrepancyId])

  async function explain() {
    setAiState('loading')
    try {
      const res = await api.explainDiscrepancy(reconciliationId, discrepancyId)
      setAi(res)
      setAiState('ready')
    } catch {
      setAiState('error')
    }
  }

  return (
    <div className="fixed inset-0 z-40 flex items-end justify-end bg-foreground/20 p-0 sm:p-6">
      <div className="flex h-full w-full max-w-lg flex-col bg-card shadow-xl sm:h-auto sm:max-h-[calc(100vh-48px)] sm:rounded-lg">
        <div className="flex items-start justify-between border-b p-5">
          <div>
            <p className="text-xs text-muted-foreground">Discrepancy detail</p>
            <h2 className="mt-1 text-xl font-semibold">{detail?.order && 'order_id' in detail.order ? String(detail.order.order_id) : 'Detail'}</h2>
          </div>
          <button onClick={onClose} className="rounded-md p-1 hover:bg-muted">
            <X className="size-5" />
          </button>
        </div>
        <div className="flex flex-col gap-5 overflow-y-auto p-5">
          {state === 'loading' && <LoadingState />}
          {state === 'error' && <ErrorState message="Unable to load this discrepancy." />}
          {state === 'ready' && detail && (
            <>
              <div className="flex items-center gap-2">
                <CategoryBadge category={detail.category} />
                <PriorityBadge priority={detail.priority} />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <DetailField label="Order amount" value={detail.order ? formatMoney(Number(detail.order.amount), detail.order_currency) : 'No matching order'} />
                <DetailField label="Payment amount" value={detail.payment ? formatMoney(Number(detail.payment.amount), detail.payment_currency) : 'No matching payment'} />
                <DetailField label="Difference" value={detail.difference !== null ? formatMoney(detail.difference, detail.order_currency ?? detail.payment_currency) : '—'} />
                <DetailField label="Financial impact" value={formatMoney(detail.financial_impact, detail.order_currency ?? detail.payment_currency)} />
              </div>
              <div className="rounded-md bg-muted/60 p-4">
                <p className="text-sm font-medium">Deterministic reason</p>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">{detail.reason}</p>
              </div>

              {aiState === 'idle' && (
                <button onClick={explain} className="flex items-center justify-center gap-2 rounded-md border py-2.5 text-sm font-medium hover:bg-muted">
                  <Sparkles className="size-4" />
                  Explain with AI
                </button>
              )}
              {aiState === 'loading' && (
                <button disabled className="flex items-center justify-center gap-2 rounded-md border py-2.5 text-sm font-medium opacity-60">
                  Analyzing...
                </button>
              )}
              {aiState === 'error' && (
                <div className="flex flex-col gap-2">
                  <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">AI explanation failed. Please try again.</p>
                  <button onClick={explain} className="rounded-md border py-2 text-sm font-medium hover:bg-muted">
                    Try again
                  </button>
                </div>
              )}
              {aiState === 'ready' && ai && (
                <div className="rounded-md border bg-accent/40 p-4">
                  <p className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-primary">
                    <Sparkles className="size-3.5" />
                    AI explanation{ai.is_fallback ? ' (unavailable)' : ''}
                  </p>
                  <p className="mt-2 text-sm"><span className="font-medium">What happened: </span>{ai.what_happened}</p>
                  <p className="mt-2 text-sm"><span className="font-medium">Likely cause: </span>{ai.likely_cause}</p>
                  <p className="mt-2 text-sm"><span className="font-medium">Recommended action: </span>{ai.recommended_action}</p>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}

function DetailField({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-sm font-medium">{value}</p>
    </div>
  )
}

function AnalyzeModal({ reconciliationId, discrepancyIds, onClose }: { reconciliationId: string; discrepancyIds: string[]; onClose: () => void }) {
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading')
  const [result, setResult] = useState<AIAnalysisResponse | null>(null)

  const run = useCallback(async () => {
    setState('loading')
    try {
      const res = await api.analyzeDiscrepancies(reconciliationId, discrepancyIds)
      setResult(res)
      setState('ready')
    } catch {
      setState('error')
    }
  }, [reconciliationId, discrepancyIds])

  useEffect(() => {
    run()
  }, [run])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/30 p-5">
      <div className="w-full max-w-md rounded-lg bg-card p-6 shadow-xl">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-2 text-sm font-medium">
              <Sparkles className="size-4 text-primary" />
              AI analysis
            </div>
            <h2 className="mt-2 text-xl font-semibold">{discrepancyIds.length} discrepancies selected</h2>
          </div>
          <button onClick={onClose}>
            <X className="size-5 text-muted-foreground" />
          </button>
        </div>

        {state === 'loading' && <LoadingState label="Analyzing..." />}
        {state === 'error' && <ErrorState message="AI analysis failed. Please try again." onRetry={run} />}
        {state === 'ready' && result && (
          <div className="mt-4">
            <p className="text-sm text-muted-foreground">
              Total financial impact: <span className="font-medium text-foreground">{formatMoney(result.total_financial_impact, 'USD')}</span>
            </p>
            <p className="mt-3 text-sm leading-6">{result.summary}</p>
            {result.recommended_actions.length > 0 && (
              <ul className="mt-3 list-inside list-disc text-sm text-muted-foreground">
                {result.recommended_actions.map((a, i) => (
                  <li key={i}>{a}</li>
                ))}
              </ul>
            )}
            {result.is_fallback && <p className="mt-3 text-xs text-muted-foreground">AI summary unavailable — showing fallback.</p>}
          </div>
        )}

        <div className="mt-5 flex justify-end gap-2">
          <button onClick={onClose} className="rounded-md border px-3 py-2 text-sm">
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
