import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
import { useCommands, useNav, type CommandItem, type NavItem } from '@/app/extensions'
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem as CommandOption, CommandList } from './ui/command'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from './ui/dialog'

const BUILT_IN_GROUPS = new Set(['actions', 'navigation'])
/** Sections whose item names can repeat an operations item ("Limpieza"), so they carry a suffix. */
const SUFFIXED_SECTIONS = new Set(['settings', 'admin'])

/** Pages (nav) and feature commands, filtered as the user types. Props-driven so it can be reused. */
export function CommandPaletteList({ nav, commands, onDone }: { nav: NavItem[]; commands: CommandItem[]; onDone: () => void }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [query, setQuery] = useState('')

  const groups = useMemo(() => {
    const byGroup = new Map<string, CommandItem[]>()
    for (const command of commands) byGroup.set(command.group, [...(byGroup.get(command.group) ?? []), command])
    return [...byGroup.entries()]
  }, [commands])

  function go(path: string) {
    navigate(path)
    onDone()
  }

  return (
    <Command loop>
      <CommandInput value={query} onValueChange={setQuery} placeholder={t('commandPalette.placeholder')} />
      <CommandList>
        <CommandEmpty>{t('commandPalette.empty')}</CommandEmpty>
        {groups.map(([group, items]) => (
          <CommandGroup key={group} heading={t(BUILT_IN_GROUPS.has(group) ? `commandPalette.${group}` : group)}>
            {items.map((command) => {
              const Icon = command.icon
              const label = t(command.labelKey)
              return (
                <CommandOption
                  key={command.id}
                  value={`${label} ${command.id}`}
                  keywords={command.keywords}
                  onSelect={() => {
                    command.perform({ navigate: (to) => navigate(to), query })
                    onDone()
                  }}
                >
                  {Icon && <Icon aria-hidden />}
                  {label}
                </CommandOption>
              )
            })}
          </CommandGroup>
        ))}
        {nav.length > 0 && (
          <CommandGroup heading={t('commandPalette.navigation')}>
            {nav.map((item) => {
              const Icon = item.icon
              const label = t(item.labelKey)
              const section = t(`nav.sections.${item.section}`)
              return (
                <CommandOption key={item.id} value={`${label} ${item.id}`} keywords={[section]} onSelect={() => go(item.path)}>
                  <Icon aria-hidden />
                  {label}
                  {SUFFIXED_SECTIONS.has(item.section) && <span className="ml-auto text-xs text-subtle">{section}</span>}
                </CommandOption>
              )
            })}
          </CommandGroup>
        )}
      </CommandList>
    </Command>
  )
}

/** ⌘K / Ctrl+K palette: every page the user can open plus the actions features register (`commands.ts`). */
export function CommandPalette({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const { t } = useTranslation()
  const nav = useNav()
  const commands = useCommands()
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent hideClose className="top-[18%] max-w-xl translate-y-0 gap-0 overflow-hidden p-0">
        <DialogTitle className="sr-only">{t('commandPalette.title')}</DialogTitle>
        <DialogDescription className="sr-only">{t('commandPalette.placeholder')}</DialogDescription>
        <CommandPaletteList nav={nav} commands={commands} onDone={() => onOpenChange(false)} />
      </DialogContent>
    </Dialog>
  )
}
