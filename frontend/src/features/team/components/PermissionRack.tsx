import { useTranslation } from 'react-i18next'
import { normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { PermissionModule } from '../api'
import { moduleCoverage } from '../permission-model'

const SLOT = {
  all: 'bg-accent',
  some: 'bg-accent-soft ring-1 ring-inset ring-accent/45',
  none: 'bg-surface-3',
}

/**
 * The shape of a role at a glance: one small tag per module, like the front-desk key rack — full when the
 * role has every permission of the module, outlined when it has some, empty when it has none.
 */
export function PermissionRack({
  id,
  name,
  value,
  catalog,
  className,
}: {
  id?: string
  name: string
  value: string[]
  catalog: PermissionModule[]
  className?: string
}) {
  const { t, i18n } = useTranslation('team')
  const lang = normalizeLang(i18n.language)
  const coverages = catalog.map((module) => ({ module, ...moduleCoverage(value, module) }))
  const reached = coverages.filter((item) => item.state !== 'none').length
  return (
    <span
      id={id}
      role="img"
      aria-label={t('roles.rack', { name, count: reached, total: catalog.length })}
      className={cn('flex flex-wrap gap-[3px]', className)}
    >
      {coverages.map(({ module, state }) => (
        <span
          key={module.code}
          title={lang === 'en' ? module.label_en : module.label_es}
          className={cn('h-2.5 w-2 rounded-[2px]', SLOT[state])}
        />
      ))}
    </span>
  )
}
