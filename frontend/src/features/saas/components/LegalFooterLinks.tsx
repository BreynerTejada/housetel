import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { cn } from '@/lib/utils'
import { LEGAL_PATHS, type LegalDocId } from '../legal/types'

/**
 * Quiet links to Housetel's legal pages for the footers of pages without Housetel's own footer (booking
 * engine, guest portal). They open in a new tab so a booking or a check-in in progress is not lost.
 */
export function LegalFooterLinks({ docs = ['privacidad', 'terminos'], className }: { docs?: LegalDocId[]; className?: string }) {
  const { t } = useTranslation('saas')
  return (
    <nav aria-label={t('legal.documents')} className={cn('text-xs text-muted', className)}>
      <ul className="flex flex-wrap items-center gap-x-3 gap-y-1">
        {docs.map((doc) => (
          <li key={doc}>
            <Link
              to={LEGAL_PATHS[doc]}
              target="_blank"
              rel="noopener"
              className="rounded-sm underline-offset-4 hover:text-fg hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55"
            >
              {t(`legal.links.${doc}`)}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  )
}
