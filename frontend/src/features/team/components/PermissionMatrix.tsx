import { Lock } from 'lucide-react'
import { useId } from 'react'
import { useTranslation } from 'react-i18next'
import { Checkbox } from '@/components/ui/checkbox'
import { Tooltip } from '@/components/ui/tooltip'
import { normalizeLang } from '@/lib/format'
import { matchPermission } from '@/lib/permissions'
import { cn } from '@/lib/utils'
import type { PermissionModule } from '../api'
import { moduleCoverage, toggleModule, togglePermission } from '../permission-model'

export interface PermissionMatrixProps {
  catalog: PermissionModule[]
  /** Role permissions: codes or patterns (`bookings.*`, `*`). */
  value: string[]
  onChange?: (value: string[]) => void
  readOnly?: boolean
  /** Permissions the current user may hand out (default: all). Others are shown locked. */
  canGrant?: (code: string) => boolean
}

/** Permissions grouped by module, with "select the whole module" per group. */
export function PermissionMatrix({ catalog, value, onChange, readOnly = false, canGrant = () => true }: PermissionMatrixProps) {
  const { t, i18n } = useTranslation('team')
  const lang = normalizeLang(i18n.language)
  const baseId = useId()
  const label = (item: { label_es: string; label_en: string }) => (lang === 'en' ? item.label_en : item.label_es)

  return (
    <div className="grid gap-3 lg:grid-cols-2">
      {catalog.map((module) => {
        const coverage = moduleCoverage(value, module)
        const grantable = module.permissions.some((permission) => canGrant(permission.code))
        const moduleLabel = label(module)
        return (
          <fieldset
            key={module.code}
            className={cn(
              'rounded-lg border border-border bg-surface transition-colors',
              coverage.state !== 'none' && 'border-accent/30',
            )}
          >
            <legend className="sr-only">{moduleLabel}</legend>
            <div className="flex items-center gap-3 border-b border-border px-3 py-2.5">
              <Checkbox
                // Inside the role form Radix adds a hidden native checkbox: it needs a name like any control.
                name="modules"
                value={module.code}
                aria-label={t('matrix.selectModule', { module: moduleLabel })}
                checked={coverage.state === 'all' ? true : coverage.state === 'some' ? 'indeterminate' : false}
                disabled={readOnly || !grantable}
                onCheckedChange={(checked) => onChange?.(toggleModule(value, module, checked === true, catalog, canGrant))}
              />
              <span aria-hidden className="flex-1 font-bold text-fg">
                {moduleLabel}
              </span>
              <span className={cn('num text-xs', coverage.state === 'none' ? 'text-subtle' : 'text-accent-ink')}>
                {t('matrix.count', { granted: coverage.granted, total: coverage.total })}
              </span>
            </div>
            <ul className="grid gap-0.5 p-1.5">
              {module.permissions.map((permission) => {
                const id = `${baseId}-${permission.code}`
                const allowed = canGrant(permission.code)
                const checked = matchPermission(value, permission.code)
                return (
                  <li key={permission.code} className="flex items-center gap-3 rounded-md px-1.5 py-1.5 hover:bg-surface-2/70">
                    <Checkbox
                      id={id}
                      name="permissions"
                      value={permission.code}
                      checked={checked}
                      disabled={readOnly || !allowed}
                      onCheckedChange={(next) => onChange?.(togglePermission(value, permission.code, next === true, catalog))}
                    />
                    <label htmlFor={id} className={cn('flex min-w-0 flex-1 flex-col', !readOnly && allowed && 'cursor-pointer')}>
                      <span className="text-[13px] leading-5 font-semibold text-fg">{label(permission)}</span>
                      <span className="num truncate font-mono text-[11px] leading-4 text-subtle">{permission.code}</span>
                    </label>
                    {!allowed && !readOnly && (
                      <Tooltip content={t('matrix.cannotGrant')}>
                        <span tabIndex={0} className="rounded-sm text-subtle focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55">
                          <Lock aria-label={t('matrix.cannotGrant')} className="size-3.5" />
                        </span>
                      </Tooltip>
                    )}
                  </li>
                )
              })}
            </ul>
          </fieldset>
        )
      })}
    </div>
  )
}
