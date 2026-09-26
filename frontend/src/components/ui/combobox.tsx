import { Check, ChevronsUpDown } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from './command'
import { fieldBase } from './input'
import { Popover, PopoverContent, PopoverTrigger } from './popover'

export interface ComboboxOption {
  value: string
  label: string
  description?: string
  keywords?: string[]
}

interface ComboboxProps {
  options: ComboboxOption[]
  value: string | null
  onChange: (value: string | null) => void
  placeholder?: string
  searchPlaceholder?: string
  emptyText?: string
  disabled?: boolean
  id?: string
  className?: string
  'aria-invalid'?: boolean
}

/** Searchable single select. Selecting the current option again clears it. */
export function Combobox({
  options,
  value,
  onChange,
  placeholder,
  searchPlaceholder,
  emptyText,
  disabled,
  id,
  className,
  ...aria
}: ComboboxProps) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const selected = options.find((option) => option.value === value)

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          id={id}
          type="button"
          role="combobox"
          aria-expanded={open}
          aria-invalid={aria['aria-invalid']}
          disabled={disabled}
          className={cn(fieldBase, 'flex h-9 items-center justify-between gap-2 px-3 text-left text-sm', className)}
        >
          <span className={cn('truncate', !selected && 'text-subtle')}>{selected?.label ?? placeholder ?? t('actions.search')}</span>
          <ChevronsUpDown aria-hidden className="size-4 shrink-0 text-muted" />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-(--radix-popover-trigger-width) min-w-56 p-0">
        <Command>
          <CommandInput placeholder={searchPlaceholder ?? t('actions.search')} />
          <CommandList>
            <CommandEmpty>{emptyText ?? t('table.empty')}</CommandEmpty>
            <CommandGroup>
              {options.map((option) => (
                <CommandItem
                  key={option.value}
                  value={`${option.label} ${option.value}`}
                  keywords={option.keywords}
                  onSelect={() => {
                    onChange(option.value === value ? null : option.value)
                    setOpen(false)
                  }}
                >
                  <Check aria-hidden className={cn('!text-accent', option.value === value ? 'opacity-100' : 'opacity-0')} />
                  <span className="flex min-w-0 flex-col">
                    <span className="truncate">{option.label}</span>
                    {option.description && <span className="truncate text-xs text-muted">{option.description}</span>}
                  </span>
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}
