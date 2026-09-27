import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Combobox } from '@/components/ui/combobox'
import { normalizeLang } from '@/lib/format'
import { countryOptions } from '../countries'

/** Searchable ISO-3166 country picker (value: two-letter code, `''` for none). */
export function CountrySelect({
  value,
  onChange,
  id,
  placeholder,
  disabled,
  className,
  'aria-invalid': ariaInvalid,
}: {
  value: string
  onChange: (value: string) => void
  id?: string
  placeholder?: string
  disabled?: boolean
  className?: string
  'aria-invalid'?: boolean
}) {
  const { t, i18n } = useTranslation('guests')
  const lang = normalizeLang(i18n.language)
  const options = useMemo(() => countryOptions(lang), [lang])
  return (
    <Combobox
      id={id}
      options={options}
      value={value || null}
      onChange={(next) => onChange(next ?? '')}
      placeholder={placeholder ?? t('fields.chooseCountry')}
      searchPlaceholder={t('fields.searchCountry')}
      emptyText={t('fields.noCountry')}
      disabled={disabled}
      className={className}
      aria-invalid={ariaInvalid}
    />
  )
}
