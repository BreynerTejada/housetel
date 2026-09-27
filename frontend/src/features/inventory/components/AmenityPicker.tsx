import { Minus, Plus } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import { AMENITY_CATEGORIES, type Amenity } from '../api'
import { amenityIcon } from '../lib/amenityIcons'
import { naturalCompare, tr } from '../lib/text'

type Props = { amenities: Amenity[]; className?: string } & (
  | { mode: 'select'; value: string[]; onChange: (value: string[]) => void }
  | {
      mode: 'inherit'
      /** Codes the category has. */
      inherited: string[]
      extra: string[]
      removed: string[]
      onChange: (value: { extra: string[]; removed: string[] }) => void
    }
)

type ChipState = 'on' | 'off' | 'inherited' | 'removed' | 'added'

/**
 * Amenities grouped like guests read them (room, bathroom, view, accessibility, property). In `inherit` mode
 * (a room): the category's amenities come already on — click to drop one for this room — and any other can be
 * added only here.
 */
export function AmenityPicker(props: Props) {
  const { t, i18n } = useTranslation('inventory')
  const groups = AMENITY_CATEGORIES.map((category) => ({
    category,
    items: props.amenities
      .filter((amenity) => amenity.category === category)
      .sort((a, b) => naturalCompare(tr(a.name, i18n.language), tr(b.name, i18n.language))),
  })).filter((group) => group.items.length > 0)

  function stateOf(code: string): ChipState {
    if (props.mode === 'select') return props.value.includes(code) ? 'on' : 'off'
    if (props.inherited.includes(code)) return props.removed.includes(code) ? 'removed' : 'inherited'
    return props.extra.includes(code) ? 'added' : 'off'
  }

  function toggle(code: string) {
    if (props.mode === 'select') {
      props.onChange(props.value.includes(code) ? props.value.filter((c) => c !== code) : [...props.value, code])
      return
    }
    const { extra, removed } = props
    switch (stateOf(code)) {
      case 'inherited':
        props.onChange({ extra, removed: [...removed, code] })
        break
      case 'removed':
        props.onChange({ extra, removed: removed.filter((c) => c !== code) })
        break
      case 'added':
        props.onChange({ extra: extra.filter((c) => c !== code), removed })
        break
      default:
        props.onChange({ extra: [...extra, code], removed })
    }
  }

  return (
    <div className={cn('grid gap-5', props.className)}>
      {groups.map(({ category, items }) => (
        <section key={category} aria-labelledby={`amenity-group-${category}`}>
          <h3 id={`amenity-group-${category}`} className="eyebrow mb-2">
            {t(`amenityCategories.${category}`)}
          </h3>
          <ul className="flex flex-wrap gap-2">
            {items.map((amenity) => {
              const state = stateOf(amenity.code)
              const Icon = amenityIcon(amenity.icon)
              const pressed = state === 'on' || state === 'inherited' || state === 'added'
              return (
                <li key={amenity.id}>
                  <button
                    type="button"
                    aria-pressed={pressed}
                    onClick={() => toggle(amenity.code)}
                    data-state={state}
                    className={cn(
                      'inline-flex h-8 items-center gap-1.5 rounded-full border px-3 text-[13px] font-medium transition-colors',
                      'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55',
                      state === 'off' && 'border-border bg-surface text-muted hover:border-border-strong hover:text-fg',
                      state === 'on' && 'border-accent bg-accent-soft text-accent-ink',
                      state === 'inherited' && 'border-dashed border-border-strong bg-surface-2 text-fg',
                      state === 'removed' && 'border-dashed border-border bg-surface text-subtle line-through',
                      state === 'added' && 'border-accent bg-accent-soft text-accent-ink',
                    )}
                  >
                    {state === 'added' ? (
                      <Plus aria-hidden className="size-3.5" />
                    ) : state === 'removed' ? (
                      <Minus aria-hidden className="size-3.5" />
                    ) : (
                      <Icon aria-hidden className="size-3.5" />
                    )}
                    {tr(amenity.name, i18n.language)}
                    {props.mode === 'inherit' && state !== 'off' && <span className="sr-only">{t(`amenities.state.${state}`)}</span>}
                  </button>
                </li>
              )
            })}
          </ul>
        </section>
      ))}
    </div>
  )
}
