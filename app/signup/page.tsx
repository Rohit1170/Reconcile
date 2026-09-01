'use client'

import { useState, type FormEvent } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { Check, Loader2 } from 'lucide-react'
import { useAuth } from '@/lib/auth'
import { ApiError } from '@/lib/api'

export default function SignupPage() {
  const { signup } = useAuth()
  const router = useRouter()
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)

    if (password !== confirmPassword) {
      setError('Passwords do not match')
      return
    }
    if (password.length < 8) {
      setError('Password must be at least 8 characters')
      return
    }

    setSubmitting(true)
    try {
      await signup(name, email, password)
      router.replace('/dashboard')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to sign up. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-5">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center gap-3 text-center">
          <div className="flex size-10 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <Check className="size-5" />
          </div>
          <div>
            <h1 className="text-xl font-semibold tracking-tight">Create your account</h1>
            <p className="mt-1 text-sm text-muted-foreground">Start reconciling orders and payments</p>
          </div>
        </div>
        <form onSubmit={onSubmit} className="flex flex-col gap-4 rounded-lg border bg-card p-6 shadow-sm">
          {error && <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>}
          <div className="flex flex-col gap-1.5">
            <label htmlFor="name" className="text-sm font-medium">Name</label>
            <input
              id="name"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="rounded-md border bg-background px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
              placeholder="Jordan Davis"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label htmlFor="email" className="text-sm font-medium">Email</label>
            <input
              id="email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="rounded-md border bg-background px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
              placeholder="you@example.com"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label htmlFor="password" className="text-sm font-medium">Password</label>
            <input
              id="password"
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="rounded-md border bg-background px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
              placeholder="At least 8 characters"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label htmlFor="confirm-password" className="text-sm font-medium">Confirm password</label>
            <input
              id="confirm-password"
              type="password"
              required
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className="rounded-md border bg-background px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
              placeholder="Re-enter your password"
            />
          </div>
          <button
            type="submit"
            disabled={submitting}
            className="mt-2 flex items-center justify-center gap-2 rounded-md bg-primary px-3 py-2.5 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-60"
          >
            {submitting && <Loader2 className="size-4 animate-spin" />}
            {submitting ? 'Creating account...' : 'Sign up'}
          </button>
        </form>
        <p className="mt-5 text-center text-sm text-muted-foreground">
          Already have an account? <Link href="/login" className="font-medium text-foreground hover:underline">Log in</Link>
        </p>
      </div>
    </div>
  )
}
