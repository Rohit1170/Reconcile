'use client'

import { useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { Check, FileText, Loader2, Sparkles, Upload as UploadIcon, X } from 'lucide-react'
import { api, ApiError } from '@/lib/api'
import { setActiveReconciliationId } from '@/lib/active-reconciliation'

type Step = 'idle' | 'uploading' | 'reconciling' | 'done' | 'error'

export default function UploadPage() {
  const router = useRouter()
  const [ordersFile, setOrdersFile] = useState<File | null>(null)
  const [paymentsFile, setPaymentsFile] = useState<File | null>(null)
  const [step, setStep] = useState<Step>('idle')
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<{ orders_imported: number; payments_imported: number } | null>(null)
  const ordersInput = useRef<HTMLInputElement>(null)
  const paymentsInput = useRef<HTMLInputElement>(null)

  async function runPipeline(uploadFn: () => Promise<{ reconciliation_id: string; orders_imported: number; payments_imported: number }>) {
    setError(null)
    setStep('uploading')
    try {
      const uploadRes = await uploadFn()
      setStep('reconciling')
      await api.runReconciliation(uploadRes.reconciliation_id)
      setActiveReconciliationId(uploadRes.reconciliation_id)
      setResult({ orders_imported: uploadRes.orders_imported, payments_imported: uploadRes.payments_imported })
      setStep('done')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong. Please try again.')
      setStep('error')
    }
  }

  function onUploadClick() {
    if (!ordersFile || !paymentsFile) return
    runPipeline(() => api.uploadDatasets(ordersFile, paymentsFile))
  }

  function onDemoClick() {
    runPipeline(() => api.loadDemoData())
  }

  const busy = step === 'uploading' || step === 'reconciling'

  return (
    <>
      <header className="flex h-16 items-center justify-between border-b bg-card px-5 lg:px-8">
        <div>
          <p className="text-sm font-medium">Upload</p>
          <p className="text-xs text-muted-foreground">Import orders and payments to reconcile</p>
        </div>
      </header>
      <div className="mx-auto max-w-2xl p-5 lg:p-8">
        {step === 'done' && result ? (
          <div className="rounded-lg border bg-card p-6 text-center">
            <div className="mx-auto flex size-10 items-center justify-center rounded-full bg-primary/10 text-primary">
              <Check className="size-5" />
            </div>
            <h2 className="mt-4 text-lg font-semibold">Reconciliation complete</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Imported {result.orders_imported} orders and {result.payments_imported} payments, and ran the deterministic
              reconciliation engine against them.
            </p>
            <button
              onClick={() => router.push('/dashboard')}
              className="mt-5 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
            >
              View dashboard
            </button>
          </div>
        ) : (
          <div className="flex flex-col gap-6">
            <div className="rounded-lg border bg-card p-6">
              <h2 className="font-semibold">Upload your files</h2>
              <p className="mt-1 text-sm text-muted-foreground">Both orders.csv and payments.csv are required.</p>

              {error && <p className="mt-4 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>}

              <div className="mt-4 flex flex-col gap-3">
                <FilePicker label="orders.csv" file={ordersFile} onPick={() => ordersInput.current?.click()} onClear={() => setOrdersFile(null)} disabled={busy} />
                <input ref={ordersInput} type="file" accept=".csv" hidden onChange={(e) => setOrdersFile(e.target.files?.[0] ?? null)} />

                <FilePicker label="payments.csv" file={paymentsFile} onPick={() => paymentsInput.current?.click()} onClear={() => setPaymentsFile(null)} disabled={busy} />
                <input ref={paymentsInput} type="file" accept=".csv" hidden onChange={(e) => setPaymentsFile(e.target.files?.[0] ?? null)} />
              </div>

              <button
                onClick={onUploadClick}
                disabled={!ordersFile || !paymentsFile || busy}
                className="mt-5 flex w-full items-center justify-center gap-2 rounded-md bg-primary px-3 py-2.5 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
              >
                {busy && <Loader2 className="size-4 animate-spin" />}
                {step === 'uploading' ? 'Uploading...' : step === 'reconciling' ? 'Reconciling...' : 'Upload and reconcile'}
              </button>
            </div>

            <div className="flex items-center gap-3 text-xs text-muted-foreground">
              <div className="h-px flex-1 bg-border" />
              or
              <div className="h-px flex-1 bg-border" />
            </div>

            <div className="flex items-center justify-between gap-4 rounded-lg border bg-card p-5">
              <div className="flex items-center gap-3">
                <Sparkles className="size-5 text-primary" />
                <div>
                  <p className="text-sm font-medium">Load demo data</p>
                  <p className="text-xs text-muted-foreground">Try the app instantly with a sample dataset</p>
                </div>
              </div>
              <button
                onClick={onDemoClick}
                disabled={busy}
                className="whitespace-nowrap rounded-md border px-3 py-2 text-sm font-medium hover:bg-muted disabled:opacity-50"
              >
                Load demo data
              </button>
            </div>
          </div>
        )}
      </div>
    </>
  )
}

function FilePicker({
  label,
  file,
  onPick,
  onClear,
  disabled,
}: {
  label: string
  file: File | null
  onPick: () => void
  onClear: () => void
  disabled: boolean
}) {
  return (
    <div className="flex items-center justify-between rounded-md border px-4 py-3">
      <div className="flex items-center gap-3">
        <FileText className="size-4 text-muted-foreground" />
        <div>
          <p className="text-sm font-medium">{label}</p>
          <p className="text-xs text-muted-foreground">{file ? file.name : 'No file selected'}</p>
        </div>
      </div>
      {file ? (
        <button onClick={onClear} disabled={disabled} className="rounded-md p-1.5 text-muted-foreground hover:bg-muted disabled:opacity-50">
          <X className="size-4" />
        </button>
      ) : (
        <button onClick={onPick} disabled={disabled} className="flex items-center gap-2 rounded-md border px-2.5 py-1.5 text-xs font-medium hover:bg-muted disabled:opacity-50">
          <UploadIcon className="size-3.5" />
          Choose file
        </button>
      )}
    </div>
  )
}
