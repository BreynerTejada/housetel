import { ChevronRight } from 'lucide-react'
import { Fragment, type ReactNode } from 'react'
import { Link } from 'react-router'
import { cn } from '@/lib/utils'

export interface Breadcrumb {
  label: ReactNode
  to?: string
}

/** Title block of a page: breadcrumbs, title, one-line description and the page's actions. */
export function PageHeader({
  title,
  description,
  actions,
  breadcrumbs,
  className,
}: {
  title: ReactNode
  description?: ReactNode
  actions?: ReactNode
  breadcrumbs?: Breadcrumb[]
  className?: string
}) {
  return (
    <header className={cn('flex flex-col gap-4 pb-6 sm:flex-row sm:items-end sm:justify-between', className)}>
      <div className="min-w-0">
        {breadcrumbs && breadcrumbs.length > 0 && (
          <nav aria-label="Breadcrumb" className="mb-2 flex flex-wrap items-center gap-1 text-[13px] text-muted">
            {breadcrumbs.map((crumb, index) => (
              <Fragment key={index}>
                {index > 0 && <ChevronRight aria-hidden className="size-3.5 text-subtle" />}
                {crumb.to ? (
                  <Link to={crumb.to} className="rounded-sm hover:text-fg hover:underline">
                    {crumb.label}
                  </Link>
                ) : (
                  <span>{crumb.label}</span>
                )}
              </Fragment>
            ))}
          </nav>
        )}
        <h1 className="text-[22px] leading-7 tracking-[-0.025em] text-fg">{title}</h1>
        {description && <p className="mt-1 max-w-2xl text-muted">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </header>
  )
}
