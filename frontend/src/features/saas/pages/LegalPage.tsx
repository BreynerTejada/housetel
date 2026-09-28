import { ArrowUp, Mail, MessageCircle, Printer } from 'lucide-react'
import { Fragment, useEffect, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, Navigate, useLocation, useParams } from 'react-router'
import { Button } from '@/components/ui/button'
import { formatDate, normalizeLang } from '@/lib/format'
import { mailtoLink, useRuntimeConfig, whatsappLink } from '@/lib/runtime'
import { cn } from '@/lib/utils'
import { en } from '../legal/en'
import { es } from '../legal/es'
import { LEGAL_DOC_IDS, LEGAL_EFFECTIVE_DATE, LEGAL_PATHS, LEGAL_VERSION, type LegalBlock, type LegalDocId } from '../legal/types'

/** English slugs people may type (`/legal/privacy`) → the canonical Spanish ones the consents link to. */
const ALIASES: Record<string, LegalDocId> = { terms: 'terminos', privacy: 'privacidad', dpa: 'encargo-datos' }
const TOKEN = /\{(email|whatsapp|privacy|terms|dpa)\}/g
const LINK_TOKENS: Record<string, LegalDocId> = { privacy: 'privacidad', terms: 'terminos', dpa: 'encargo-datos' }

function docFromParam(value: string | undefined): LegalDocId | null {
  if (!value) return null
  if ((LEGAL_DOC_IDS as readonly string[]).includes(value)) return value as LegalDocId
  return ALIASES[value] ?? null
}

/**
 * `/legal/terminos`, `/legal/privacidad` and `/legal/encargo-datos` (plan P6): Housetel's terms, the personal
 * data policy (Ley 1581 de 2012) and the data processing agreement between each hotel and Housetel, in Spanish
 * and English. The consents of the checkout, the online check-in and the signup link here (in a new tab).
 */
export default function LegalPage() {
  const { doc: param } = useParams()
  const doc = docFromParam(param)
  if (!doc) return <Navigate to={LEGAL_PATHS.terminos} replace />
  if (param !== doc) return <Navigate to={LEGAL_PATHS[doc]} replace />
  return <LegalDocumentView doc={doc} />
}

function LegalDocumentView({ doc }: { doc: LegalDocId }) {
  const { t, i18n } = useTranslation('saas')
  const lang = normalizeLang(i18n.language)
  const texts = lang === 'en' ? en : es
  const document = texts[doc]
  const { hash } = useLocation()
  const { support } = useRuntimeConfig()

  // A deep link to a clause (`/legal/privacidad#derechos`) lands on it once the page has rendered.
  useEffect(() => {
    if (!hash) {
      window.scrollTo({ top: 0 })
      return
    }
    window.document.getElementById(decodeURIComponent(hash.slice(1)))?.scrollIntoView()
  }, [doc, hash])

  /** Paragraph text with its placeholders turned into the support contact and links to the other documents. */
  function rich(text: string): ReactNode {
    const parts: ReactNode[] = []
    let last = 0
    for (const match of text.matchAll(TOKEN)) {
      const [token, name] = match
      const index = match.index ?? 0
      parts.push(text.slice(last, index))
      last = index + token.length
      if (name === 'email') {
        const href = mailtoLink(support.email)
        parts.push(
          href ? (
            <a key={index} href={href} className="font-semibold text-accent-ink underline-offset-4 hover:underline">
              {support.email}
            </a>
          ) : (
            t('legal.noEmail')
          ),
        )
      } else if (name === 'whatsapp') {
        const href = whatsappLink(support.whatsapp)
        parts.push(
          href ? (
            <a key={index} href={href} target="_blank" rel="noreferrer" className="num font-semibold text-accent-ink underline-offset-4 hover:underline">
              {support.whatsapp}
            </a>
          ) : (
            t('legal.noWhatsapp')
          ),
        )
      } else {
        const target = LINK_TOKENS[name!]!
        parts.push(
          <Link key={index} to={LEGAL_PATHS[target]} className="font-semibold text-accent-ink underline-offset-4 hover:underline">
            {texts[target].title.charAt(0).toLocaleLowerCase(lang) + texts[target].title.slice(1)}
          </Link>,
        )
      }
    }
    parts.push(text.slice(last))
    return parts.map((part, index) => <Fragment key={index}>{part}</Fragment>)
  }

  function block(item: LegalBlock, index: number) {
    if (typeof item === 'string') {
      return (
        <p key={index} className="leading-relaxed text-fg/90">
          {rich(item)}
        </p>
      )
    }
    if ('list' in item) {
      return (
        <ul key={index} className="grid gap-2 pl-1">
          {item.list.map((entry, position) => (
            <li key={position} className="flex gap-3 leading-relaxed text-fg/90">
              <span aria-hidden className="mt-[0.7em] size-1.5 shrink-0 rounded-full bg-accent" />
              <span className="min-w-0">{rich(entry)}</span>
            </li>
          ))}
        </ul>
      )
    }
    return (
      <p key={index} className="rounded-xl border border-accent/25 bg-accent-soft/60 px-4 py-3 leading-relaxed text-fg">
        {rich(item.note)}
      </p>
    )
  }

  const effective = formatDate(LEGAL_EFFECTIVE_DATE, lang === 'en' ? 'MMMM d, yyyy' : "d 'de' MMMM 'de' yyyy", lang)
  const email = mailtoLink(support.email, document.title)
  const whatsapp = whatsappLink(support.whatsapp, document.title)

  return (
    <article className="mx-auto w-full max-w-6xl px-4 pt-10 pb-20 sm:px-6 sm:pt-14 print:pt-0" aria-labelledby="legal-title">
      <p className="eyebrow text-accent-ink">{t('legal.eyebrow', { version: LEGAL_VERSION, date: effective })}</p>
      <h1 id="legal-title" className="mt-4 max-w-[18ch] text-[clamp(2.2rem,6vw,3.6rem)] leading-[0.98] font-extrabold tracking-[-0.045em] text-fg">
        {document.title}
      </h1>
      <p className="mt-5 max-w-2xl text-lg leading-relaxed text-muted">{document.lead}</p>

      <nav aria-label={t('legal.documents')} className="mt-8 print:hidden">
        <ul className="flex flex-wrap gap-2">
          {LEGAL_DOC_IDS.map((id) => {
            const active = id === doc
            return (
              <li key={id}>
                <Link
                  to={LEGAL_PATHS[id]}
                  aria-current={active ? 'page' : undefined}
                  className={cn(
                    // a key tag: rounded plate with the punched hole of the Housetel mark
                    'inline-flex min-h-10 items-center gap-2.5 rounded-lg border py-2 pr-3 pl-3.5 text-left text-sm leading-5 font-bold transition-colors',
                    'focus-visible:ring-2 focus-visible:ring-accent/55 focus-visible:ring-offset-2 focus-visible:ring-offset-bg focus-visible:outline-none',
                    active ? 'border-accent bg-accent text-on-accent shadow-xs' : 'border-border bg-surface text-fg hover:border-border-strong',
                  )}
                >
                  {texts[id].title}
                  <span aria-hidden className={cn('size-2 rounded-full', active ? 'bg-bg' : 'border border-border-strong bg-bg')} />
                </Link>
              </li>
            )
          })}
        </ul>
      </nav>

      <div className="mt-10 grid gap-10 lg:grid-cols-[15rem_minmax(0,1fr)] lg:gap-14">
        <aside className="print:hidden">
          <details className="group rounded-xl border border-border bg-surface px-4 py-3 lg:hidden">
            <summary className="cursor-pointer text-sm font-bold text-fg">{t('legal.contents')}</summary>
            <SectionIndex sections={document.sections} className="mt-3" />
          </details>
          <div className="sticky top-24 hidden lg:block">
            <p className="eyebrow">{t('legal.onThisPage')}</p>
            <SectionIndex sections={document.sections} className="mt-3" />
          </div>
        </aside>

        <div className="grid min-w-0 content-start gap-10">
          <section aria-labelledby="legal-summary" className="rounded-2xl border border-border bg-surface p-5 shadow-xs sm:p-6">
            <h2 id="legal-summary" className="eyebrow text-accent-ink">
              {t('legal.inShort')}
            </h2>
            <ul className="mt-3 grid gap-2.5">
              {document.summary.map((item, index) => (
                <li key={index} className="flex gap-3 leading-relaxed text-fg">
                  <span aria-hidden className="mt-[0.7em] size-1.5 shrink-0 rounded-full bg-accent" />
                  <span className="min-w-0">{rich(item)}</span>
                </li>
              ))}
            </ul>
            <p className="mt-4 text-sm text-muted">{t('legal.fullTextBelow')}</p>
          </section>

          {document.sections.map((section) => (
            <section key={section.id} id={section.id} aria-labelledby={`${section.id}-title`} className="grid scroll-mt-24 gap-3.5">
              <h2 id={`${section.id}-title`} className="text-xl leading-tight font-extrabold tracking-[-0.02em] text-fg sm:text-2xl">
                <a href={`#${section.id}`} className="group/anchor rounded-sm focus-visible:ring-2 focus-visible:ring-accent/55 focus-visible:outline-none">
                  {section.title}
                  <span aria-hidden className="ml-2 text-subtle opacity-0 transition-opacity group-hover/anchor:opacity-100 group-focus-visible/anchor:opacity-100">
                    #
                  </span>
                </a>
              </h2>
              {section.body.map(block)}
            </section>
          ))}

          <footer className="grid gap-4 rounded-2xl border border-border bg-surface-2/70 p-5 sm:p-6 print:hidden">
            <div>
              <h2 className="text-lg font-extrabold tracking-[-0.02em] text-fg">{t('legal.questionsTitle')}</h2>
              <p className="mt-1 text-sm text-muted">{t('legal.questionsBody')}</p>
            </div>
            <div className="flex flex-wrap gap-2">
              {email && (
                <Button asChild>
                  <a href={email}>
                    <Mail aria-hidden />
                    {support.email}
                  </a>
                </Button>
              )}
              {whatsapp && (
                <Button asChild>
                  <a href={whatsapp} target="_blank" rel="noreferrer">
                    <MessageCircle aria-hidden />
                    {t('legal.whatsapp')}
                  </a>
                </Button>
              )}
              <Button variant="ghost" onClick={() => window.print()}>
                <Printer aria-hidden />
                {t('legal.print')}
              </Button>
              <Button variant="ghost" onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}>
                <ArrowUp aria-hidden />
                {t('legal.backToTop')}
              </Button>
            </div>
            {lang === 'en' && <p className="text-xs text-muted">{t('legal.spanishPrevails')}</p>}
          </footer>
        </div>
      </div>
    </article>
  )
}

function SectionIndex({ sections, className }: { sections: { id: string; title: string }[]; className?: string }) {
  return (
    <ol className={cn('grid gap-1 text-sm', className)}>
      {sections.map((section) => (
        <li key={section.id}>
          <a
            href={`#${section.id}`}
            className="block rounded-md py-1 leading-snug text-muted transition-colors hover:text-fg focus-visible:ring-2 focus-visible:ring-accent/55 focus-visible:outline-none"
          >
            {section.title}
          </a>
        </li>
      ))}
    </ol>
  )
}
