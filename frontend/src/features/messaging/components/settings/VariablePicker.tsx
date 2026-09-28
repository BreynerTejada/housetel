import { Braces } from 'lucide-react'
import { Fragment } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { normalizeLang } from '@/lib/format'
import type { Variable } from '../../api'

const GROUPS: Variable['group'][] = ['guest', 'reservation', 'property', 'links', 'payment']

/** "Insert variable": the `{{placeholders}}` a template can use, by group, with their label and key. */
export function VariablePicker({ variables, onPick, disabled }: { variables: Variable[]; onPick: (key: string) => void; disabled?: boolean }) {
  const { t, i18n } = useTranslation('messaging')
  const lang = normalizeLang(i18n.language)
  const groups = GROUPS.map((group) => ({ group, items: variables.filter((item) => item.group === group) })).filter(
    (entry) => entry.items.length > 0,
  )

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button type="button" variant="ghost" size="sm" disabled={disabled}>
          <Braces aria-hidden />
          {t('settings.templates.variables')}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="max-h-[22rem] w-72 overflow-y-auto">
        <p className="px-2 pt-1.5 pb-2 text-[12px] leading-snug text-muted">{t('settings.templates.variablesHint')}</p>
        {groups.map(({ group, items }, index) => (
          <Fragment key={group}>
            {index > 0 && <DropdownMenuSeparator />}
            <DropdownMenuLabel>{t(`settings.templates.groups.${group}`)}</DropdownMenuLabel>
            {items.map((item) => (
              <DropdownMenuItem key={item.key} onSelect={() => onPick(item.key)} className="flex-col items-start gap-0">
                <span>{item.label[lang]}</span>
                <span className="num text-[11px] text-muted">{`{{${item.key}}}`}</span>
              </DropdownMenuItem>
            ))}
          </Fragment>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
