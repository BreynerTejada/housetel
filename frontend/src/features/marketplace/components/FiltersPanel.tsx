import { useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { MoneyInput } from '@/components/Money'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { cn } from '@/lib/utils'
import type { SearchResponse } from '../api'
import type { SearchState } from '../lib/search-params'
import { tr } from '../lib/text'
import { AmenityIcon } from './AmenityIcon'
import { Stars } from './Stars'

type Facets = SearchResponse['facets']

function toggle<T>(list: T[], value: T): T[] {
  return list.includes(value) ? list.filter((item) => item !== value) : [...list, value]
}

function Group({ legend, children }: { legend: string; children: ReactNode }) {
  return (
    <fieldset className="border-t border-border pt-5 first:border-t-0 first:pt-0">
      <legend className="mb-3 text-sm font-bold text-fg">{legend}</legend>
      <div className="grid gap-2.5">{children}</div>
    </fieldset>
  )
}

function Option({ checked, onChange, children }: { checked: boolean; onChange: () => void; children: ReactNode }) {
  return (
    <label className="flex cursor-pointer items-center gap-2.5 text-sm text-fg">
      <Checkbox checked={checked} onCheckedChange={onChange} />
      {children}
    </label>
  )
}

interface FiltersPanelProps {
  state: SearchState
  facets: Facets | undefined
  currency?: string
  onChange: (patch: Partial<SearchState>) => void
  className?: string
}

/** Price per night, type, stars and amenities (the options and counts come from the destination's hotels). */
export function FiltersPanel({ state, facets, currency = 'COP', onChange, className }: FiltersPanelProps) {
  const { t, i18n } = useTranslation(['marketplace', 'common'])
  const [minPrice, setMinPrice] = useState(state.minPrice)
  const [maxPrice, setMaxPrice] = useState(state.maxPrice)
  const [syncedPrices, setSyncedPrices] = useState(`${state.minPrice}|${state.maxPrice}`)
  if (syncedPrices !== `${state.minPrice}|${state.maxPrice}`) {
    setSyncedPrices(`${state.minPrice}|${state.maxPrice}`)
    setMinPrice(state.minPrice)
    setMaxPrice(state.maxPrice)
  }
  const priceChanged = minPrice !== state.minPrice || maxPrice !== state.maxPrice
  const count = (value: number) => <span className="num ml-auto text-xs text-subtle">{t('results.facetCount', { count: value })}</span>

  return (
    <div className={cn('grid gap-5', className)}>
      <Group legend={t('results.price')}>
        <p className="-mt-2 text-xs text-muted">{t('results.priceHint')}</p>
        <div className="grid grid-cols-2 gap-2">
          <MoneyInput aria-label={t('results.minPrice')} placeholder={t('results.minPrice')} value={minPrice} onChange={setMinPrice} currency={currency} />
          <MoneyInput aria-label={t('results.maxPrice')} placeholder={t('results.maxPrice')} value={maxPrice} onChange={setMaxPrice} currency={currency} />
        </div>
        {priceChanged && (
          <Button size="sm" onClick={() => onChange({ minPrice, maxPrice })}>
            {t('results.applyPrice')}
          </Button>
        )}
      </Group>

      {facets && facets.types.length > 0 && (
        <Group legend={t('results.type')}>
          {facets.types.map((facet) => (
            <Option key={facet.value} checked={state.types.includes(facet.value)} onChange={() => onChange({ types: toggle(state.types, facet.value) })}>
              <span>{t(`common:propertyTypes.${facet.value}`, { defaultValue: facet.value })}</span>
              {count(facet.count)}
            </Option>
          ))}
        </Group>
      )}

      {facets && facets.stars.length > 0 && (
        <Group legend={t('results.stars')}>
          {facets.stars.map((facet) => (
            <Option key={facet.value} checked={state.stars.includes(facet.value)} onChange={() => onChange({ stars: toggle(state.stars, facet.value) })}>
              <Stars count={facet.value} />
              {count(facet.count)}
            </Option>
          ))}
        </Group>
      )}

      {facets && facets.amenities.length > 0 && (
        <Group legend={t('results.amenities')}>
          {facets.amenities.map((amenity) => (
            <Option
              key={amenity.code}
              checked={state.amenities.includes(amenity.code)}
              onChange={() => onChange({ amenities: toggle(state.amenities, amenity.code) })}
            >
              <AmenityIcon name={amenity.icon} aria-hidden className="size-4 text-muted" />
              <span>{tr(amenity.name, i18n.language)}</span>
              {count(amenity.count)}
            </Option>
          ))}
        </Group>
      )}
    </div>
  )
}
