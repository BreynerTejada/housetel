import { CalendarRange, MapPin, Search, UsersRound } from 'lucide-react'
import type { FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router'

// Provisional marketplace home (Phase A): hero + search box without real search. C4 replaces it.
export default function HomePage() {
  const { t } = useTranslation('marketplace')
  const navigate = useNavigate()

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const destination = String(new FormData(event.currentTarget).get('destination') ?? '').trim()
    navigate(destination ? `/search?city=${encodeURIComponent(destination)}` : '/search')
  }

  return (
    <div className="mx-auto w-full max-w-6xl px-4 sm:px-6">
      <section className="pb-16 pt-14 sm:pb-24 sm:pt-24">
        <p className="eyebrow text-accent-ink">{t('home.eyebrow')}</p>
        <h1 className="mt-4 max-w-3xl text-5xl leading-[1.02] font-extrabold tracking-[-0.035em] text-fg sm:text-7xl">
          {t('home.title')}
        </h1>
        <p className="mt-6 max-w-xl text-lg text-muted">{t('home.subtitle')}</p>

        <form
          onSubmit={onSubmit}
          aria-label={t('home.searchLabel')}
          className="mt-10 grid gap-2 rounded-2xl border border-border bg-surface p-2 shadow-sm sm:grid-cols-[1.4fr_1fr_1fr_auto]"
        >
          <label className="flex items-center gap-3 rounded-xl px-4 py-3 focus-within:bg-surface-2">
            <MapPin aria-hidden className="size-5 shrink-0 text-accent" />
            <span className="flex min-w-0 flex-1 flex-col">
              <span className="text-xs font-semibold text-muted">{t('home.destination')}</span>
              <input
                name="destination"
                placeholder={t('home.destinationPlaceholder')}
                className="w-full bg-transparent text-base text-fg outline-none"
              />
            </span>
          </label>
          <div className="flex items-center gap-3 rounded-xl px-4 py-3 sm:border-l sm:border-border">
            <CalendarRange aria-hidden className="size-5 shrink-0 text-muted" />
            <span className="flex flex-col">
              <span className="text-xs font-semibold text-muted">{t('home.dates')}</span>
              <span className="text-base text-subtle">— · —</span>
            </span>
          </div>
          <div className="flex items-center gap-3 rounded-xl px-4 py-3 sm:border-l sm:border-border">
            <UsersRound aria-hidden className="size-5 shrink-0 text-muted" />
            <span className="flex flex-col">
              <span className="text-xs font-semibold text-muted">{t('home.guests')}</span>
              <span className="text-base text-fg">{t('home.guestsValue')}</span>
            </span>
          </div>
          <button
            type="submit"
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-accent px-6 py-3 text-base font-semibold text-on-accent transition-colors hover:bg-accent-hover"
          >
            <Search aria-hidden className="size-5" />
            {t('home.search')}
          </button>
        </form>
      </section>

      <section className="mb-20 flex flex-col items-start justify-between gap-6 border-t border-border pt-10 sm:flex-row sm:items-end">
        <div className="max-w-lg">
          <h2 className="text-2xl text-fg">{t('home.hotelsTitle')}</h2>
          <p className="mt-2 text-muted">{t('home.hotelsBody')}</p>
        </div>
        <Link
          to="/signup"
          className="inline-flex items-center rounded-lg border border-border-strong bg-surface px-5 py-2.5 font-semibold text-fg transition-colors hover:border-accent hover:text-accent-ink"
        >
          {t('home.hotelsCta')}
        </Link>
      </section>
    </div>
  )
}
