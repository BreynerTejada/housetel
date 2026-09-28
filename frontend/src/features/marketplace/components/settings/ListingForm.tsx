import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, ArrowRight, Check, Plus, Trash2 } from 'lucide-react'
import { useId, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { errorMessage } from '@/lib/errors'
import { cn } from '@/lib/utils'
import { marketplaceKeys, patchListingSettings, type I18nText, type ListingSettings, type ListingSettingsInput, type PropertyCard } from '../../api'
import { tr } from '../../lib/text'
import { HotelTile } from '../Cards'
import { SaveBar, SettingsSection } from './SettingsBits'

const MAX_HIGHLIGHTS = 6
const MAX_FEATURED = 12

type Draft = Required<ListingSettingsInput>

function draftOf(listing: ListingSettings): Draft {
  return {
    marketplace_listed: listing.marketplace_listed,
    tagline: listing.tagline ?? {},
    highlights: listing.highlights ?? [],
    neighborhood: listing.neighborhood ?? '',
    featured_photo_ids: listing.featured_photo_ids ?? [],
  }
}

function changes(draft: Draft, listing: ListingSettings): ListingSettingsInput {
  const original = draftOf(listing)
  const diff: Record<string, unknown> = {}
  for (const key of Object.keys(draft) as (keyof Draft)[]) {
    if (JSON.stringify(draft[key]) !== JSON.stringify(original[key])) diff[key] = draft[key]
  }
  return diff as ListingSettingsInput
}

function move<T>(list: T[], from: number, to: number): T[] {
  const next = [...list]
  const [item] = next.splice(from, 1)
  next.splice(to, 0, item as T)
  return next
}

/** How the hotel shows up in the marketplace: listed or not, card line, neighborhood, highlights, featured photos. */
export function ListingForm({ listing }: { listing: ListingSettings }) {
  const { t, i18n } = useTranslation(['marketplace', 'common'])
  const queryClient = useQueryClient()
  const uid = useId()
  const [draft, setDraft] = useState<Draft>(() => draftOf(listing))
  const diff = changes(draft, listing)
  const dirty = Object.keys(diff).length > 0
  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => setDraft((current) => ({ ...current, [key]: value }))

  const save = useMutation({
    mutationFn: () => patchListingSettings({ ...diff, ...(diff.highlights ? { highlights: diff.highlights.filter((item) => item.es || item.en) } : {}) }),
    onSuccess: (saved) => {
      queryClient.setQueryData(marketplaceKeys.listingSettings, saved)
      setDraft(draftOf(saved))
      toast.success(t('settings.saved'))
    },
    onError: (error) => toast.error(errorMessage(error, t)),
  })

  function togglePhoto(id: string) {
    const featured = draft.featured_photo_ids
    if (featured.includes(id)) set('featured_photo_ids', featured.filter((photo) => photo !== id))
    else if (featured.length < MAX_FEATURED) set('featured_photo_ids', [...featured, id])
  }

  const cover = listing.photos.find((photo) => photo.id === draft.featured_photo_ids[0]) ?? listing.photos[0]
  const preview: PropertyCard = {
    slug: 'preview',
    name: listing.name,
    property_type: listing.property_type,
    star_rating: listing.star_rating,
    city: listing.city,
    department: '',
    neighborhood: draft.neighborhood,
    tagline: draft.tagline,
    highlights: draft.highlights,
    photo: cover?.url ?? null,
    photos: [],
    amenities: [],
    currency: 'COP',
    offer: null,
  }

  return (
    <div className="grid gap-8 xl:grid-cols-[minmax(0,1fr)_17rem]">
      <div className="min-w-0">
        <SettingsSection title={t('settings.listing.visibility')}>
          <label className="flex items-start justify-between gap-4">
            <span>
              <span className="block text-sm font-semibold text-fg">{t('settings.listing.listed')}</span>
              <span className="block text-xs text-muted">{t('settings.listing.listedHint')}</span>
            </span>
            <Switch checked={draft.marketplace_listed} onCheckedChange={(value) => set('marketplace_listed', value)} aria-label={t('settings.listing.listed')} />
          </label>
        </SettingsSection>

        <SettingsSection title={t('settings.listing.content')}>
          <fieldset className="grid gap-2">
            <legend className="text-[13px] font-semibold text-fg">{t('settings.listing.tagline')}</legend>
            <p className="-mt-1 text-xs text-muted">{t('settings.listing.taglineHint')}</p>
            <div className="grid gap-2 sm:grid-cols-2">
              {(['es', 'en'] as const).map((lang) => (
                <Input
                  key={lang}
                  aria-label={lang === 'es' ? t('settings.listing.taglineEs') : t('settings.listing.taglineEn')}
                  placeholder={lang === 'es' ? t('settings.engine.spanish') : t('settings.engine.english')}
                  value={draft.tagline[lang] ?? ''}
                  maxLength={140}
                  onChange={(event) => set('tagline', { ...draft.tagline, [lang]: event.target.value })}
                />
              ))}
            </div>
          </fieldset>
          <div className="grid gap-1.5">
            <Label htmlFor={`${uid}-neighborhood`}>{t('settings.listing.neighborhood')}</Label>
            <Input
              id={`${uid}-neighborhood`}
              value={draft.neighborhood}
              maxLength={100}
              placeholder={t('settings.listing.neighborhoodPlaceholder')}
              onChange={(event) => set('neighborhood', event.target.value)}
              className="max-w-sm"
            />
          </div>
          <fieldset className="grid gap-2">
            <legend className="text-[13px] font-semibold text-fg">{t('settings.listing.highlights')}</legend>
            <p className="-mt-1 text-xs text-muted">{t('settings.listing.highlightsHint')}</p>
            <ol className="grid gap-2">
              {draft.highlights.map((highlight, index) => (
                <li key={index} className="grid gap-2 sm:grid-cols-[1fr_1fr_auto]">
                  {(['es', 'en'] as const).map((lang) => (
                    <Input
                      key={lang}
                      aria-label={`${t('settings.listing.highlight', { number: index + 1 })} · ${lang === 'es' ? t('settings.engine.spanish') : t('settings.engine.english')}`}
                      placeholder={lang === 'es' ? t('settings.engine.spanish') : t('settings.engine.english')}
                      value={highlight[lang] ?? ''}
                      maxLength={120}
                      onChange={(event) =>
                        set(
                          'highlights',
                          draft.highlights.map((item, i): I18nText => (i === index ? { ...item, [lang]: event.target.value } : item)),
                        )
                      }
                    />
                  ))}
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label={t('settings.listing.removeHighlight', { number: index + 1 })}
                    onClick={() => set('highlights', draft.highlights.filter((_, i) => i !== index))}
                  >
                    <Trash2 aria-hidden />
                  </Button>
                </li>
              ))}
            </ol>
            {draft.highlights.length < MAX_HIGHLIGHTS && (
              <Button size="sm" className="w-fit" onClick={() => set('highlights', [...draft.highlights, { es: '', en: '' }])}>
                <Plus aria-hidden />
                {t('settings.listing.addHighlight')}
              </Button>
            )}
          </fieldset>
          <div className="grid gap-1">
            <p className="text-[13px] font-semibold text-fg">{t('settings.listing.description')}</p>
            <p className="max-w-2xl text-sm whitespace-pre-line text-muted">{tr(listing.description, i18n.language) || '—'}</p>
            <p className="text-xs text-muted">
              {t('settings.listing.descriptionHint')}{' '}
              <Link to="/app/settings/property" className="font-semibold text-accent-ink hover:underline">
                {t('settings.listing.editDescription')}
              </Link>
            </p>
          </div>
        </SettingsSection>

        <SettingsSection title={t('settings.listing.photos')} hint={t('settings.listing.photosHint')}>
          {listing.photos.length === 0 ? (
            <p className="text-sm text-muted">
              {t('settings.listing.noPhotos')}{' '}
              <Link to="/app/settings/property" className="font-semibold text-accent-ink hover:underline">
                {t('settings.listing.managePhotos')}
              </Link>
            </p>
          ) : (
            <ul role="group" aria-label={t('settings.listing.photos')} className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
              {listing.photos.map((photo) => {
                const position = draft.featured_photo_ids.indexOf(photo.id)
                const chosen = position >= 0
                return (
                  <li key={photo.id} className={cn('overflow-hidden rounded-lg border bg-surface', chosen ? 'border-accent ring-2 ring-accent/30' : 'border-border')}>
                    <div className="relative aspect-[4/3] bg-surface-2">
                      <img src={photo.url} alt="" className="size-full object-cover" loading="lazy" />
                      {chosen && (
                        <span className="num absolute top-1.5 left-1.5 grid size-6 place-items-center rounded-full bg-accent text-xs font-bold text-on-accent" aria-label={t('settings.listing.photoOrder', { number: position + 1 })}>
                          {position + 1}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-1 px-2 py-1.5">
                      <span className="min-w-0 flex-1 truncate text-xs text-muted">
                        {photo.room_type ? `${photo.room_type.code} · ${tr(photo.room_type.name, i18n.language)}` : t('settings.listing.hotelPhoto')}
                      </span>
                      {chosen && (
                        <>
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            aria-label={t('settings.listing.moveEarlier')}
                            disabled={position === 0}
                            onClick={() => set('featured_photo_ids', move(draft.featured_photo_ids, position, position - 1))}
                          >
                            <ArrowLeft aria-hidden />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            aria-label={t('settings.listing.moveLater')}
                            disabled={position === draft.featured_photo_ids.length - 1}
                            onClick={() => set('featured_photo_ids', move(draft.featured_photo_ids, position, position + 1))}
                          >
                            <ArrowRight aria-hidden />
                          </Button>
                        </>
                      )}
                      <Button
                        variant={chosen ? 'subtle' : 'ghost'}
                        size="icon-sm"
                        aria-label={chosen ? t('settings.listing.unchoosePhoto') : t('settings.listing.choosePhoto')}
                        aria-pressed={chosen}
                        disabled={!chosen && draft.featured_photo_ids.length >= MAX_FEATURED}
                        onClick={() => togglePhoto(photo.id)}
                      >
                        {chosen ? <Check aria-hidden className="text-accent" /> : <Plus aria-hidden />}
                      </Button>
                    </div>
                  </li>
                )
              })}
            </ul>
          )}
        </SettingsSection>
        <SaveBar visible={dirty} saving={save.isPending} onSave={() => save.mutate()} onDiscard={() => setDraft(draftOf(listing))} />
      </div>
      <div className="xl:sticky xl:top-20 xl:self-start">
        <p className="mb-2 text-[11px] font-semibold text-muted">{t('settings.listing.preview')}</p>
        <div className="pointer-events-none rounded-xl border border-border bg-bg p-3" aria-hidden>
          <HotelTile hotel={preview} href="#" />
        </div>
      </div>
    </div>
  )
}
