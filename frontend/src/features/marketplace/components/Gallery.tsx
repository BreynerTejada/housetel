import { ChevronLeft, ChevronRight, Images } from 'lucide-react'
import { useState, type KeyboardEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog'
import { cn } from '@/lib/utils'
import type { Photo as PhotoData } from '../api'
import { tr } from '../lib/text'
import { Photo } from './Cards'

/** Desktop mosaic layout by photo count: the first photo is always the big one. */
const TILE: Record<number, string[]> = {
  1: ['col-span-4 row-span-2'],
  2: ['col-span-2 row-span-2', 'col-span-2 row-span-2'],
  3: ['col-span-2 row-span-2', 'col-span-2', 'col-span-2'],
  4: ['col-span-2 row-span-2', 'col-span-2', 'col-span-1', 'col-span-1'],
  5: ['col-span-2 row-span-2', 'col-span-1', 'col-span-1', 'col-span-1', 'col-span-1'],
}

/** The hotel's photos: a mosaic on wide screens, a swipeable strip on phones, and a lightbox for all of them. */
export function Gallery({ photos, name }: { photos: PhotoData[]; name: string }) {
  const { t, i18n } = useTranslation('marketplace')
  const [open, setOpen] = useState<number | null>(null)
  if (photos.length === 0) {
    return (
      <div className="grid h-48 place-items-center rounded-2xl border border-dashed border-border-strong bg-surface-2 text-sm text-muted">
        {t('hotel.noPhotos')}
      </div>
    )
  }
  const shown = photos.slice(0, 5)
  const tiles = TILE[shown.length] ?? TILE[5]!
  const current = open === null ? null : photos[open]

  function onKeyDown(event: KeyboardEvent) {
    if (open === null) return
    if (event.key === 'ArrowRight') setOpen((open + 1) % photos.length)
    if (event.key === 'ArrowLeft') setOpen((open - 1 + photos.length) % photos.length)
  }

  return (
    <section aria-label={t('hotel.gallery', { name })}>
      {/* phones: swipe */}
      <ul className="-mx-4 flex snap-x snap-mandatory gap-2 overflow-x-auto px-4 [scrollbar-width:none] sm:hidden">
        {photos.map((photo, index) => (
          <li key={photo.id} className="w-[86%] shrink-0 snap-center">
            <button
              type="button"
              onClick={() => setOpen(index)}
              aria-label={t('hotel.photo', { number: index + 1, total: photos.length })}
              className="block w-full overflow-hidden rounded-xl outline-none focus-visible:ring-2 focus-visible:ring-accent/55"
            >
              <Photo src={photo.url} alt={tr(photo.caption, i18n.language)} className="aspect-[4/3]" />
            </button>
          </li>
        ))}
      </ul>
      {/* wide screens: mosaic */}
      <div className="relative hidden h-[25rem] grid-cols-4 grid-rows-2 gap-2 overflow-hidden rounded-2xl sm:grid lg:h-[28rem]">
        {shown.map((photo, index) => (
          <button
            key={photo.id}
            type="button"
            onClick={() => setOpen(index)}
            aria-label={t('hotel.photo', { number: index + 1, total: photos.length })}
            className={cn('group relative overflow-hidden outline-none focus-visible:ring-2 focus-visible:ring-accent/55 focus-visible:ring-inset', tiles[index])}
          >
            <Photo src={photo.url} alt={tr(photo.caption, i18n.language)} className="size-full" />
          </button>
        ))}
        {photos.length > 1 && (
          <Button size="sm" className="absolute right-3 bottom-3 shadow-md" onClick={() => setOpen(0)}>
            <Images aria-hidden />
            {t('hotel.allPhotos', { count: photos.length })}
          </Button>
        )}
      </div>

      <Dialog open={open !== null} onOpenChange={(next) => !next && setOpen(null)}>
        <DialogContent className="max-w-5xl gap-3 bg-surface p-3 sm:p-4" onKeyDown={onKeyDown}>
          <DialogTitle className="pr-10 text-base">
            {name} · {t('hotel.photo', { number: (open ?? 0) + 1, total: photos.length })}
          </DialogTitle>
          {current && (
            <figure>
              <img src={current.url} alt={tr(current.caption, i18n.language)} className="max-h-[70dvh] w-full rounded-lg bg-surface-2 object-contain" />
              {tr(current.caption, i18n.language) && (
                <figcaption className="mt-2 text-sm text-muted">{tr(current.caption, i18n.language)}</figcaption>
              )}
            </figure>
          )}
          {photos.length > 1 && (
            <div className="flex justify-between">
              <Button aria-label={t('hotel.prevPhoto')} onClick={() => setOpen(((open ?? 0) - 1 + photos.length) % photos.length)}>
                <ChevronLeft aria-hidden />
              </Button>
              <Button aria-label={t('hotel.nextPhoto')} onClick={() => setOpen(((open ?? 0) + 1) % photos.length)}>
                <ChevronRight aria-hidden />
              </Button>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </section>
  )
}
