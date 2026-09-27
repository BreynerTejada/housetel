import type { TFunction } from 'i18next'
import { formatNumber, normalizeLang } from '@/lib/format'
import type { BedConfig, CategoryAttributes, OverridableField } from '../api'
import { tr } from './text'

/** Suggested view codes (the backend accepts any text; these get translated labels). */
export const VIEW_CODES = ['sea', 'city', 'garden', 'pool', 'mountain', 'courtyard', 'interior', 'panoramic', 'street'] as const

export const OCCUPANCY_FIELDS = ['base_occupancy', 'max_adults', 'max_children', 'max_occupancy'] as const
export type OccupancyField = (typeof OCCUPANCY_FIELDS)[number]
export type Occupancy = Record<OccupancyField, number>

export function viewLabel(view: string, t: TFunction): string {
  if (!view) return t('inventory:common.none')
  const key = `inventory:views.${view}`
  return t(key, { defaultValue: view })
}

export function bedsSummary(beds: BedConfig[] | null | undefined, t: TFunction): string {
  if (!beds?.length) return t('inventory:common.none')
  return beds.map((bed) => `${bed.count} × ${t(`inventory:bedTypes.${bed.type}`)}`).join(' · ')
}

export function sizeLabel(size: string | number | null | undefined, lang: string): string {
  if (size === null || size === undefined || size === '') return '—'
  const value = Number(size)
  return Number.isFinite(value) ? `${formatNumber(value, normalizeLang(lang))} m²` : '—'
}

/** Human text of one category attribute (for inherited values and hints). */
export function attributeText(field: OverridableField, value: unknown, t: TFunction, lang: string): string {
  switch (field) {
    case 'name':
    case 'description':
      return tr(value as CategoryAttributes['name'], lang) || t('inventory:common.none')
    case 'beds':
      return bedsSummary(value as BedConfig[], t)
    case 'size_m2':
      return sizeLabel(value as string | null, lang)
    case 'view':
      return viewLabel(String(value ?? ''), t)
    case 'smoking_allowed':
    case 'accessible':
      return value ? t('inventory:common.yes') : t('inventory:common.no')
    case 'housekeeping_minutes':
      return t('inventory:common.minutes', { count: Number(value) })
    default:
      return String(value ?? '—')
  }
}

/**
 * Same consistency rules as the backend (`occupancy_errors`): base ≤ max, adults ≤ max,
 * children ≤ max − 1. Returns i18n messages keyed by field.
 */
export function occupancyErrors(values: Occupancy, t: TFunction): Partial<Record<OccupancyField, string>> {
  const errors: Partial<Record<OccupancyField, string>> = {}
  const max = values.max_occupancy
  if (!Number.isFinite(max) || max < 1) {
    errors.max_occupancy = t('inventory:validation.minOne')
    return errors
  }
  if (values.base_occupancy > max) errors.base_occupancy = t('inventory:validation.aboveMax', { max })
  if (values.max_adults > max) errors.max_adults = t('inventory:validation.aboveMax', { max })
  if (values.max_children > max - 1) errors.max_children = t('inventory:validation.childrenNeedAdult')
  if (values.base_occupancy < 1) errors.base_occupancy = t('inventory:validation.minOne')
  if (values.max_adults < 1) errors.max_adults = t('inventory:validation.minOne')
  if (values.max_children < 0) errors.max_children = t('inventory:validation.minZero')
  return errors
}
