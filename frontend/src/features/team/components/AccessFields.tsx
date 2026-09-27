import { Lock } from 'lucide-react'
import { useId } from 'react'
import { useTranslation } from 'react-i18next'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import type { PropertySummary } from '@/lib/auth'
import type { Role } from '../api'

export interface AccessValue {
  roleId: string
  allProperties: boolean
  propertyIds: string[]
}

/**
 * Role + hotels of a person. Roles with permissions the current user lacks are listed but locked; someone
 * restricted to some hotels (`allowAll={false}`) can only give access to those hotels (`properties`).
 */
export function AccessFields({
  value,
  onChange,
  roles,
  properties,
  propertiesError,
  disabled,
  allowAll = true,
}: {
  value: AccessValue
  onChange: (value: AccessValue) => void
  roles: Role[]
  properties: PropertySummary[]
  propertiesError?: string | null
  disabled?: boolean
  allowAll?: boolean
}) {
  const { t } = useTranslation('team')
  const baseId = useId()
  const selected = roles.find((role) => role.id === value.roleId)

  return (
    <>
      <div className="grid gap-1.5">
        <Label htmlFor={`${baseId}-role`}>{t('inviteDialog.role')}</Label>
        <Select
          name="role"
          value={value.roleId} // '' (no role yet) shows the placeholder and keeps the select controlled
          onValueChange={(roleId) => onChange({ ...value, roleId })}
          disabled={disabled}
        >
          <SelectTrigger id={`${baseId}-role`} aria-label={t('inviteDialog.role')}>
            <SelectValue placeholder={t('inviteDialog.role')} />
          </SelectTrigger>
          <SelectContent>
            {roles.map((role) => (
              <SelectItem key={role.id} value={role.id} disabled={!role.assignable}>
                <span className="flex items-center gap-2">
                  {role.name}
                  {!role.assignable && (
                    <span className="inline-flex items-center gap-1 text-xs text-subtle">
                      <Lock aria-hidden className="size-3" />
                      {t('inviteDialog.roleLocked')}
                    </span>
                  )}
                </span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {selected?.description && <p className="text-xs text-muted">{selected.description}</p>}
      </div>

      <fieldset className="grid gap-2">
        <legend className="mb-1.5 text-[13px] font-semibold text-fg">{t('inviteDialog.access')}</legend>
        <RadioGroup
          name="access_scope"
          value={value.allProperties ? 'all' : 'some'}
          onValueChange={(choice) => onChange({ ...value, allProperties: choice === 'all' })}
          disabled={disabled}
        >
          <label className={allowAll ? 'flex items-start gap-2.5' : 'flex items-start gap-2.5 opacity-70'}>
            <RadioGroupItem value="all" className="mt-0.5" disabled={!allowAll} aria-describedby={`${baseId}-all-hint`} />
            <span className="grid">
              <span className="text-sm font-semibold text-fg">{t('inviteDialog.allProperties')}</span>
              <span id={`${baseId}-all-hint`} className="text-xs text-muted">
                {allowAll ? t('inviteDialog.allPropertiesHint') : t('inviteDialog.allPropertiesLocked')}
              </span>
            </span>
          </label>
          <label className="flex items-center gap-2.5">
            <RadioGroupItem value="some" />
            <span className="text-sm font-semibold text-fg">{t('inviteDialog.someProperties')}</span>
          </label>
        </RadioGroup>
        {!value.allProperties && (
          <ul className="ml-6 grid gap-2 rounded-lg border border-border bg-surface-2/50 p-3">
            {properties.map((property) => {
              const id = `${baseId}-${property.id}`
              const checked = value.propertyIds.includes(property.id)
              return (
                <li key={property.id} className="flex items-center gap-2.5">
                  <Checkbox
                    id={id}
                    name="property_ids"
                    checked={checked}
                    disabled={disabled}
                    onCheckedChange={(next) =>
                      onChange({
                        ...value,
                        propertyIds: next === true ? [...value.propertyIds, property.id] : value.propertyIds.filter((pid) => pid !== property.id),
                      })
                    }
                  />
                  <Label htmlFor={id} className="font-medium">
                    {property.name}
                  </Label>
                </li>
              )
            })}
          </ul>
        )}
        {propertiesError && (
          <p className="text-xs font-medium text-danger-ink" aria-live="polite">
            {propertiesError}
          </p>
        )}
      </fieldset>
    </>
  )
}
