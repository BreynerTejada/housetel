import { useQueryClient } from '@tanstack/react-query'
import type { TFunction } from 'i18next'
import { useLocation } from 'react-router'
import { ME_QUERY_KEY, resolveActiveProperty, type Me } from '@/lib/auth'
import { mailtoLink, whatsappLink, type SupportContact } from '@/lib/runtime'
import { useSession } from '@/lib/session'

/** What support needs to know without asking: where the person was and who they are (plan P1). */
export interface SupportContext {
  hotel: string
  user: string
  page: string
  time: string
  /** Extra line, e.g. the error message on the error screen. */
  detail?: string
}

/**
 * Path without anything secret: no query string, and long segments (guest-portal tokens, password-reset and
 * invitation tokens) replaced by "…". Slugs, reservation ids of staff pages and short words stay.
 */
export function safePath(pathname: string): string {
  const staff = /^\/(app|admin)(\/|$)/.test(pathname)
  return (
    pathname
      .split('/')
      .map((segment) => (segment.length > (staff ? 40 : 20) ? '…' : segment))
      .join('/') || '/'
  )
}

/**
 * Support context from what is already cached: never fetches `/accounts/me/` (on public pages that call would
 * answer 401 for anonymous visitors).
 */
export function useSupportContext(detail?: string): SupportContext {
  const queryClient = useQueryClient()
  const { pathname } = useLocation()
  const storedPropertyId = useSession((state) => state.propertyId)
  const me = queryClient.getQueryData<Me | null>(ME_QUERY_KEY) ?? null
  const property = resolveActiveProperty(me, storedPropertyId)?.property
  const user = me ? [me.full_name, me.email].filter(Boolean).join(' · ') : ''
  return {
    hotel: property?.name ?? '',
    user,
    page: safePath(pathname),
    time: new Date().toLocaleString(document.documentElement.lang === 'en' ? 'en-US' : 'es-CO', {
      dateStyle: 'medium',
      timeStyle: 'short',
    }),
    detail,
  }
}

/** Lines of the context block (label, value), skipping what is unknown. */
export function contextLines(context: SupportContext, t: TFunction): [string, string][] {
  const lines: [string, string][] = [
    [t('support.context.hotel'), context.hotel],
    [t('support.context.user'), context.user],
    [t('support.context.page'), context.page],
    [t('support.context.time'), context.time],
    [t('support.context.detail'), context.detail ?? ''],
  ]
  return lines.filter(([, value]) => value)
}

/** The text that opens the WhatsApp chat / goes in the e-mail body. */
export function supportMessage(context: SupportContext, t: TFunction): string {
  const lines = contextLines(context, t).map(([label, value]) => `${label}: ${value}`)
  return [t('support.messageIntro'), '', ...lines, '', t('support.messageOutro')].join('\n')
}

export interface SupportLinks {
  whatsapp: string | null
  email: string | null
  docs: string | null
}

export function supportLinks(support: SupportContact, context: SupportContext, t: TFunction): SupportLinks {
  const message = supportMessage(context, t)
  const subject = context.hotel ? t('support.emailSubject', { hotel: context.hotel }) : t('support.emailSubjectNoHotel')
  return {
    whatsapp: whatsappLink(support.whatsapp, message),
    email: mailtoLink(support.email, subject, message),
    docs: support.docs_url || null,
  }
}
