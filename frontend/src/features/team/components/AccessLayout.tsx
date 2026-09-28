import { ArrowLeft } from 'lucide-react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { cn } from '@/lib/utils'

/**
 * Public account pages (forgot / reset password), laid out like the login: the key-card scene on the left
 * (desktop only; it repeats what the text says) and the task on the right.
 */
export function AccessLayout({ eyebrow, scene, children }: { eyebrow: string; scene: ReactNode; children: ReactNode }) {
  return (
    <div className="mx-auto grid w-full max-w-6xl flex-1 gap-10 px-4 py-8 sm:px-6 lg:grid-cols-[1.05fr_1fr] lg:gap-16 lg:py-12">
      <section aria-hidden className="hidden flex-col rounded-2xl border border-border bg-surface-2 p-10 lg:flex">
        <p className="eyebrow !text-accent-ink">{eyebrow}</p>
        <div className="flex flex-1 items-center justify-center py-12">{scene}</div>
      </section>
      <section className="flex flex-col justify-center">
        <div className="mx-auto w-full max-w-sm">{children}</div>
      </section>
    </div>
  )
}

export function BackToLogin() {
  const { t } = useTranslation('team')
  return (
    <p className="mt-8 text-sm">
      <Link
        to="/login"
        className="inline-flex items-center gap-1.5 rounded-sm font-semibold text-accent-ink underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55"
      >
        <ArrowLeft aria-hidden className="size-4" />
        {t('forgot.backToLogin')}
      </Link>
    </p>
  )
}

/** Development only: where the emails of these flows land (Mailpit, see docker-compose). */
export function DevMailboxHint({ className = 'mt-6' }: { className?: string }) {
  const { t } = useTranslation('team')
  if (!import.meta.env.DEV) return null
  return (
    <p className={cn('rounded-lg border border-dashed border-border-strong px-3 py-2.5 text-xs text-muted', className)}>
      {t('forgot.devMailbox')}{' '}
      <a
        href="http://localhost:8025"
        target="_blank"
        rel="noreferrer"
        className="num font-semibold text-accent-ink underline-offset-4 hover:underline"
      >
        localhost:8025
      </a>
    </p>
  )
}
