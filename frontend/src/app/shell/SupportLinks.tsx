import { BookOpenText, Mail, MessageCircle } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useRuntimeConfig } from '@/lib/runtime'
import { cn } from '@/lib/utils'
import { supportLinks, useSupportContext } from './support'

const linkClass =
  'inline-flex items-center gap-1.5 rounded-md px-1 py-0.5 font-semibold text-accent-ink underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55'

/**
 * One quiet line under an error or a 404: how to reach Housetel support (WhatsApp, e-mail, guides from
 * `support_contact`). The message it opens already names the screen and, when the error screen passes it,
 * what failed. Renders nothing when the installation offers no channel.
 */
export function SupportLinks({ lead, detail, className }: { lead: string; detail?: string; className?: string }) {
  const { t } = useTranslation()
  const { support } = useRuntimeConfig()
  const context = useSupportContext(detail)
  const links = supportLinks(support, context, t)
  if (!links.whatsapp && !links.email && !links.docs) return null

  return (
    <div className={cn('mt-8 border-t border-border pt-5 text-sm text-muted', className)}>
      <p>{lead}</p>
      <ul className="mt-2 flex flex-wrap items-center justify-center gap-x-3 gap-y-1">
        {links.whatsapp && (
          <li>
            <a className={linkClass} href={links.whatsapp} target="_blank" rel="noopener noreferrer">
              <MessageCircle aria-hidden className="size-4" />
              {t('support.inline.whatsapp')}
            </a>
          </li>
        )}
        {links.email && (
          <li>
            <a className={linkClass} href={links.email}>
              <Mail aria-hidden className="size-4" />
              <span className="num">{support.email}</span>
            </a>
          </li>
        )}
        {links.docs && (
          <li>
            <a className={linkClass} href={links.docs} target="_blank" rel="noopener noreferrer">
              <BookOpenText aria-hidden className="size-4" />
              {t('support.inline.docs')}
            </a>
          </li>
        )}
      </ul>
    </div>
  )
}
