import { ChevronsUpDown, Hotel } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useActiveProperty, type PropertyAccess } from '@/lib/auth'
import { formatDate, normalizeLang } from '@/lib/format'
import { useMediaQuery } from '@/lib/hooks'

/** Active property; with several, a menu grouped by organization (a chain shows all its hotels). */
export function PropertySwitcher() {
  const { t, i18n } = useTranslation()
  const { property, membership, properties, setProperty } = useActiveProperty()
  // On phones the topbar has no room for the business-date chip, so the date moves under the name.
  const isPhone = useMediaQuery('(max-width: 639px)')
  if (!property || !membership) return null
  const organizations = new Set(properties.map((access) => access.membership.organization.id))

  const label = (
    <span className="flex min-w-0 flex-1 flex-col text-left leading-tight">
      <span className="truncate text-[13.5px] font-bold text-fg">{property.name}</span>
      {organizations.size > 1 && (
        <span className="hidden truncate text-[11px] text-muted sm:block">{membership.organization.name}</span>
      )}
      {isPhone && (
        <span className="num truncate text-[11px] text-muted">
          {formatDate(property.business_date, 'EEE d MMM', normalizeLang(i18n.language))}
        </span>
      )}
    </span>
  )

  if (properties.length < 2) {
    return (
      <div className="flex min-w-0 flex-1 items-center gap-2 px-1 sm:flex-none">
        <Hotel aria-hidden className="size-4 shrink-0 text-subtle" />
        {label}
      </div>
    )
  }

  const byOrganization = new Map<string, PropertyAccess[]>()
  for (const access of properties) {
    const key = access.membership.organization.id
    byOrganization.set(key, [...(byOrganization.get(key) ?? []), access])
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          title={t('topbar.switchProperty')}
          className="flex min-w-0 flex-1 items-center gap-2 rounded-md px-2 py-1 transition-colors sm:flex-none hover:bg-surface-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55 data-[state=open]:bg-surface-2"
        >
          <Hotel aria-hidden className="size-4 shrink-0 text-subtle" />
          {label}
          <ChevronsUpDown aria-hidden className="size-3.5 shrink-0 text-subtle" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-72">
        <DropdownMenuRadioGroup value={property.id} onValueChange={setProperty}>
          {[...byOrganization.values()].map((group, index) => (
            <div key={group[0]!.membership.organization.id}>
              {index > 0 && <DropdownMenuSeparator />}
              <DropdownMenuLabel>{group[0]!.membership.organization.name}</DropdownMenuLabel>
              {group.map(({ property: item }) => (
                <DropdownMenuRadioItem key={item.id} value={item.id}>
                  <span className="flex min-w-0 flex-col">
                    <span className="truncate font-semibold">{item.name}</span>
                    <span className="text-xs text-muted">{t(`propertyTypes.${item.property_type}`)}</span>
                  </span>
                </DropdownMenuRadioItem>
              ))}
            </div>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
