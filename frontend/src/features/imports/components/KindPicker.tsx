import { BedDouble, CalendarRange, DoorOpen, Users, type LucideIcon } from 'lucide-react'
import { RadioGroup as RadioGroupPrimitive } from 'radix-ui'
import { useTranslation } from 'react-i18next'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import { KINDS, type ImportKind, type ImportPreset } from '../api'

const ICONS: Record<ImportKind, LucideIcon> = {
  reservations: CalendarRange,
  guests: Users,
  room_types: BedDouble,
  rooms: DoorOpen,
}

const OPTIONAL: ImportKind[] = ['room_types', 'rooms']

/** Step 1: what the file brings (reservations, guests, and optionally categories or rooms). */
export function KindPicker({ value, onChange }: { value: ImportKind; onChange: (kind: ImportKind) => void }) {
  const { t } = useTranslation('imports')
  return (
    <RadioGroupPrimitive.Root
      value={value}
      onValueChange={(next) => onChange(next as ImportKind)}
      aria-label={t('start.kindLabel')}
      className="grid gap-2.5 sm:grid-cols-2"
    >
      {KINDS.map((kind) => {
        const Icon = ICONS[kind]
        const selected = value === kind
        return (
          <RadioGroupPrimitive.Item
            key={kind}
            value={kind}
            className={cn(
              'group flex items-start gap-3 rounded-xl border bg-surface p-3.5 text-left shadow-xs transition-[border-color,box-shadow,background-color]',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55',
              selected ? 'border-accent bg-accent-soft/40 shadow-sm' : 'border-border hover:border-border-strong',
            )}
          >
            <span
              aria-hidden
              className={cn(
                'grid size-9 shrink-0 place-items-center rounded-lg border transition-colors',
                selected ? 'border-accent/30 bg-surface text-accent-ink' : 'border-border bg-surface-2 text-muted',
              )}
            >
              <Icon className="size-[18px]" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <span className="text-[15px] font-bold tracking-[-0.01em] text-fg">{t(`kinds.${kind}.label`)}</span>
                {OPTIONAL.includes(kind) && <Badge tone="neutral">{t('start.optional')}</Badge>}
              </span>
              <span className="mt-0.5 block text-[13px] leading-5 text-muted">{t(`kinds.${kind}.description`)}</span>
            </span>
            <span
              aria-hidden
              className={cn(
                'mt-0.5 grid size-4 shrink-0 place-items-center rounded-full border transition-colors',
                selected ? 'border-accent' : 'border-border-strong',
              )}
            >
              <RadioGroupPrimitive.Indicator className="size-2 rounded-full bg-accent" />
            </span>
          </RadioGroupPrimitive.Item>
        )
      })}
    </RadioGroupPrimitive.Root>
  )
}

/** Step 1b: where the file comes from (a Cloudbeds export or any spreadsheet / other PMS). */
export function PresetPicker({ value, onChange }: { value: ImportPreset; onChange: (preset: ImportPreset) => void }) {
  const { t } = useTranslation('imports')
  return (
    <RadioGroupPrimitive.Root
      value={value}
      onValueChange={(next) => onChange(next as ImportPreset)}
      aria-label={t('start.presetLabel')}
      className="grid gap-2.5 sm:grid-cols-2"
    >
      {(['cloudbeds', 'generic'] as const).map((preset) => {
        const selected = value === preset
        return (
          <RadioGroupPrimitive.Item
            key={preset}
            value={preset}
            className={cn(
              'flex items-start gap-3 rounded-xl border bg-surface p-3.5 text-left shadow-xs transition-[border-color,box-shadow,background-color]',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55',
              selected ? 'border-accent bg-accent-soft/40 shadow-sm' : 'border-border hover:border-border-strong',
            )}
          >
            <span className="min-w-0 flex-1">
              <span className="block text-sm font-bold text-fg">{t(`presets.${preset}.label`)}</span>
              <span className="mt-0.5 block text-[13px] leading-5 text-muted">{t(`presets.${preset}.description`)}</span>
            </span>
            <span
              aria-hidden
              className={cn(
                'mt-0.5 grid size-4 shrink-0 place-items-center rounded-full border transition-colors',
                selected ? 'border-accent' : 'border-border-strong',
              )}
            >
              <RadioGroupPrimitive.Indicator className="size-2 rounded-full bg-accent" />
            </span>
          </RadioGroupPrimitive.Item>
        )
      })}
    </RadioGroupPrimitive.Root>
  )
}
