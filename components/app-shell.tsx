'use client'

import { useEffect, type ReactNode } from 'react'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { AlertTriangle, Check, LayoutDashboard, LogOut, Upload } from 'lucide-react'
import { useAuth } from '@/lib/auth'

const nav = [
  { label: 'Dashboard', href: '/dashboard', icon: LayoutDashboard },
  { label: 'Discrepancies', href: '/discrepancies', icon: AlertTriangle },
  { label: 'Upload', href: '/upload', icon: Upload },
]

export function AppShell({ children }: { children: ReactNode }) {
  const { user, loading, logout } = useAuth()
  const pathname = usePathname()
  const router = useRouter()

  useEffect(() => {
    if (!loading && !user) router.replace('/login')
  }, [loading, user, router])

  if (loading || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-muted-foreground">
        Loading...
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-background text-foreground">
      <aside className="fixed inset-y-0 left-0 z-20 hidden w-64 border-r bg-card lg:flex lg:flex-col">
        <div className="flex h-16 items-center gap-3 border-b px-6">
          <div className="flex size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <Check className="size-4" />
          </div>
          <span className="text-lg font-semibold tracking-tight">reconcile</span>
        </div>
        <div className="flex flex-1 flex-col px-3 py-5">
          <p className="px-3 pb-3 text-xs font-medium uppercase tracking-wider text-muted-foreground">Workspace</p>
          <nav className="flex flex-col gap-1">
            {nav.map(({ label, href, icon: Icon }) => (
              <Link
                key={href}
                href={href}
                className={`flex items-center gap-3 rounded-md px-3 py-2.5 text-sm transition-colors ${
                  pathname === href
                    ? 'bg-accent font-medium text-accent-foreground'
                    : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                }`}
              >
                <Icon className="size-4" />
                {label}
              </Link>
            ))}
          </nav>
        </div>
        <div className="border-t p-4">
          <div className="flex items-center gap-3">
            <div className="flex size-8 items-center justify-center rounded-full bg-secondary text-xs font-medium">
              {user.name.slice(0, 2).toUpperCase()}
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">{user.name}</p>
              <p className="truncate text-xs text-muted-foreground">{user.email}</p>
            </div>
            <button onClick={logout} title="Log out" className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground">
              <LogOut className="size-4" />
            </button>
          </div>
        </div>
      </aside>
      <main className="lg:pl-64">{children}</main>
    </div>
  )
}
