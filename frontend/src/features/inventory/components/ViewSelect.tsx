import { useTranslation } from 'react-i18next'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { VIEW_CODES } from '../lib/attributes'

const NONE = '__none__'

/** What the room looks out to. Known views are translated; an unknown saved value stays selectable. */
export function ViewSelect({
  value,
  onChange,
  labelledBy,
  name = 'view',
  id,
}: {
  value: string
  onChange: (value: string) => void
  labelledBy?: string
  name?: string
  id?: string
}) {
  const { t } = useTranslation('inventory')
  const options: string[] = [...VIEW_CODES]
  if (value && !options.includes(value)) options.push(value)
  return (
    <Select name={name} value={value || NONE} onValueChange={(next) => onChange(next === NONE ? '' : next)}>
      <SelectTrigger id={id} aria-labelledby={labelledBy} className="w-full sm:w-64">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={NONE}>{t('views.none')}</SelectItem>
        {options.map((code) => (
          <SelectItem key={code} value={code}>
            {t(`views.${code}`, { defaultValue: code })}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
