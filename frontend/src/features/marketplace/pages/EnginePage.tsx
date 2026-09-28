import { MapPin } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useParams } from 'react-router'
import type { EngineConfig, PropertyDetail } from '../api'
import { PlaceFacts } from '../components/Cards'
import { EngineShell, EngineUnavailable } from '../components/EngineShell'
import { Gallery } from '../components/Gallery'
import { HotelView } from '../components/HotelView'
import { Stars } from '../components/Stars'
import { tr } from '../lib/text'

function EngineHero({ hotel, config }: { hotel: PropertyDetail; config: EngineConfig }) {
  const { t, i18n } = useTranslation(['marketplace', 'common'])
  const headline = tr(config.headline, i18n.language) || tr(hotel.tagline, i18n.language)
  // the image the hotel chose for its engine opens the gallery
  const photos = config.hero_image
    ? [{ id: 'hero', url: config.hero_image, caption: {} }, ...hotel.photos.filter((photo) => photo.url !== config.hero_image)]
    : hotel.photos
  return (
    <div className="pt-6">
      <Gallery photos={photos} name={hotel.name} />
      <header className="mt-7 max-w-3xl">
        <p className="flex flex-wrap items-center gap-2 text-sm font-semibold text-muted">
          {t(`common:propertyTypes.${hotel.property_type}`, { defaultValue: hotel.property_type })}
          <Stars count={hotel.star_rating} />
        </p>
        <h1 className="mt-2 text-4xl leading-[1.02] font-extrabold tracking-[-0.04em] text-fg sm:text-5xl">{hotel.name}</h1>
        {headline && <p className="mt-3 text-xl leading-snug text-fg/85">{headline}</p>}
        <p className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted">
          <MapPin aria-hidden className="size-4 text-accent" />
          {[hotel.address, hotel.neighborhood, hotel.city].filter(Boolean).join(', ')}
          <span aria-hidden>·</span>
          <PlaceFacts city={hotel.city} />
        </p>
      </header>
    </div>
  )
}

/** `/h/:slug` — the hotel's own booking engine: its brand, its rates for the engine, the same booking flow. */
export default function EnginePage() {
  const { slug = '' } = useParams()
  return (
    <EngineShell slug={slug}>
      {(config) => (
        <HotelView
          slug={slug}
          via="booking_engine"
          hero={(hotel) => <EngineHero hotel={hotel} config={config} />}
          notFound={<EngineUnavailable config={config} />}
        />
      )}
    </EngineShell>
  )
}
