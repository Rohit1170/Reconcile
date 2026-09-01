'use client'

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { AlertTriangle, CreditCard, FileText, ShieldAlert } from 'lucide-react'
import { api, ApiError, type ReconciliationSummary } from '@/lib/api'
import { getActiveReconciliationId } from '@/lib/active-reconciliation'
import { EmptyState, ErrorState, LoadingState } from '@/components/state-views'

function formatCurrency(value: number) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(value)
}

export default function DashboardPage() {
  const [summary, setSummary] = useState<ReconciliationSummary | null>(null)
  const [state, setState] = useState<'loading' | 'ready' | 'error' | 'empty'>('loading')
  const [errorMessage, setErrorMessage] = useState('')

  const load = useCallback(async () => {
    const id = getActiveReconciliationId()
    if (!id) {
      setState('empty')
      return
    }
    setState('loading')
    try {
      const data = await api.getSummary(id)
      setSummary(data)
      setState('ready')
    } catch (err) {
      setErrorMessage(err instanceof ApiError ? err.message : 'Unable to load dashboard.')
      setState('error')
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  return (
    <>
      <header className="flex h-16 items-center justify-between border-b bg-card px-5 lg:px-8">
        <div>
          <p className="text-sm font-medium">Dashboard</p>
          <p className="text-xs text-muted-foreground">Reconciliation overview</p>
        </div>
      </header>
      <div className="mx-auto max-w-[1440px] p-5 lg:p-8">
        {state === 'loading' && <LoadingState label="Loading dashboard..." />}
        {state === 'error' && <ErrorState message={errorMessage} onRetry={load} />}
        {state === 'empty' && (
          <EmptyState
            title="No reconciliation yet"
            description="Upload your orders.csv and payments.csv, or load the demo dataset, to see your dashboard."
            action={
              <Link href="/upload" className="rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:opacity-90">
                Go to Upload
              </Link>
            }
          />
        )}
        {state === 'ready' && summary && (
          <>
            <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <Metric icon={FileText} label="Total orders" value={String(summary.total_orders)} />
              <Metric icon={CreditCard} label="Total payments" value={String(summary.total_payments)} />
              <Metric icon={ShieldAlert} label="Reconciled value" value={formatCurrency(summary.matched_value)} />
              <Metric
                icon={AlertTriangle}
                label="Money at risk"
                value={formatCurrency(summary.money_at_risk)}
                warning={summary.money_at_risk > 0}
              />
            </section>

            <section className="mt-6 grid gap-4 sm:grid-cols-2">
              <div className="rounded-lg border bg-card p-5">
                <p className="text-sm text-muted-foreground">Disputed value</p>
                <p className="mt-2 text-2xl font-semibold tracking-tight">{formatCurrency(summary.disputed_value)}</p>
                <p className="mt-1 text-xs text-muted-foreground">Order/payment value involved in open discrepancies</p>
              </div>
              <div className="rounded-lg border bg-card p-5">
                <p className="text-sm text-muted-foreground">Matched vs. flagged</p>
                <p className="mt-2 text-2xl font-semibold tracking-tight">
                  {summary.matched_count} / {summary.matched_count + summary.discrepancy_count}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">{summary.discrepancy_count} discrepancies need review</p>
              </div>
            </section>

            <section className="mt-6 rounded-lg border bg-card">
              <div className="border-b p-5">
                <h2 className="font-semibold">Discrepancy breakdown</h2>
                <p className="mt-1 text-sm text-muted-foreground">Count by category, as classified by the reconciliation engine</p>
              </div>
              <div className="h-80 p-5">
                {summary.discrepancies_by_type.length === 0 ? (
                  <p className="flex h-full items-center justify-center text-sm text-muted-foreground">No discrepancies to chart.</p>
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={summary.discrepancies_by_type} layout="vertical" margin={{ left: 24 }}>
                      <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                      <XAxis type="number" allowDecimals={false} />
                      <YAxis type="category" dataKey="category" width={150} tick={{ fontSize: 12 }} />
                      <Tooltip formatter={(value, name) => [value, name === 'count' ? 'Count' : name]} />
                      <Bar dataKey="count" fill="var(--color-primary)" radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </div>
            </section>

            <div className="mt-6 flex justify-end">
              <Link
                href="/discrepancies"
                className="inline-flex items-center gap-2 rounded-md border bg-card px-3 py-2 text-sm font-medium shadow-sm hover:bg-muted"
              >
                View all discrepancies
              </Link>
            </div>
          </>
        )}
      </div>
    </>
  )
}

function Metric({ icon: Icon, label, value, warning }: { icon: typeof FileText; label: string; value: string; warning?: boolean }) {
  return (
    <div className="rounded-lg border bg-card p-5">
      <div className="flex items-center justify-between">
        <span className="text-sm text-muted-foreground">{label}</span>
        <Icon className={`size-4 ${warning ? 'text-destructive' : 'text-muted-foreground'}`} />
      </div>
      <div className="mt-3">
        <span className={`text-2xl font-semibold tracking-tight ${warning ? 'text-destructive' : ''}`}>{value}</span>
      </div>
    </div>
  )
}
