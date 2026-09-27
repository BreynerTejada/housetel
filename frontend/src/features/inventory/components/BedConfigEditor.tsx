import { Minus, Plus, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { BED_CONFIG_TYPES, type BedConfig, type BedConfigType } from '../api'

/** The beds of a category or room: one row per bed type with a count (1–20). */
export function BedConfigEditor({
  value,
  onChange,
  labelledBy,
  name = 'beds',
}: {
  value: BedConfig[]
  onChange: (value: BedConfig[]) => void
  labelledBy?: string
  name?: string
}) {
  const { t } = useTranslation('inventory')
  const used = new Set(value.map((bed) => bed.type))
  const next = BED_CONFIG_TYPES.find((type) => !used.has(type))

  function update(index: number, patch: Partial<BedConfig>) {
    onChange(value.map((bed, i) => (i === index ? { ...bed, ...patch } : bed)))
  }

  return (
    <div className="grid gap-2" aria-labelledby={labelledBy} role="list">
      {value.map((bed, index) => (
        <div key={`${bed.type}-${index}`} role="listitem" className="flex flex-wrap items-center gap-2">
          <Select
            name={`${name}.${index}.type`}
            value={bed.type}
            onValueChange={(type) => update(index, { type: type as BedConfigType })}
          >
            <SelectTrigger className="w-44" aria-label={t('beds.typeOf', { index: index + 1 })}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {BED_CONFIG_TYPES.map((type) => (
                <SelectItem key={type} value={type} disabled={type !== bed.type && used.has(type)}>
                  {t(`bedTypes.${type}`)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <div className="flex items-center rounded-md border border-border bg-surface shadow-xs">
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label={t('beds.fewer', { type: t(`bedTypes.${bed.type}`) })}
              disabled={bed.count <= 1}
              onClick={() => update(index, { count: bed.count - 1 })}
            >
              <Minus aria-hidden />
            </Button>
            <span className="num w-8 text-center text-sm font-semibold" aria-live="polite">
              {bed.count}
            </span>
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label={t('beds.more', { type: t(`bedTypes.${bed.type}`) })}
              disabled={bed.count >= 20}
              onClick={() => update(index, { count: bed.count + 1 })}
            >
              <Plus aria-hidden />
            </Button>
          </div>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={t('beds.remove', { type: t(`bedTypes.${bed.type}`) })}
            onClick={() => onChange(value.filter((_, i) => i !== index))}
          >
            <X aria-hidden />
          </Button>
        </div>
      ))}
      {next && (
        <Button variant="subtle" size="sm" className="w-fit" onClick={() => onChange([...value, { type: next, count: 1 }])}>
          <Plus aria-hidden />
          {t('beds.add')}
        </Button>
      )}
    </div>
  )
}
