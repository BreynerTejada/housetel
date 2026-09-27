import { Pencil, Trash2, X } from 'lucide-react'
import { useId, useState, type FormEvent, type ReactNode } from 'react'
import { Controller, type Control, type FieldPath, type FieldValues } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { DatePicker } from '@/components/DatePicker'
import { FormField } from '@/components/FormField'
import { MoneyInput } from '@/components/Money'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { cn } from '@/lib/utils'

/** Create/edit dialog around a form: fields, a general error (if any) and Cancel / submit. */
export function FormDialog({
  open,
  onOpenChange,
  title,
  description,
  submitLabel,
  pending,
  error,
  onSubmit,
  children,
  className,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description?: string
  submitLabel: string
  pending: boolean
  error?: string | null
  onSubmit: (event: FormEvent<HTMLFormElement>) => void
  children: ReactNode
  className?: string
}) {
  const { t } = useTranslation()
  return (
    <Dialog open={open} onOpenChange={(next) => !pending && onOpenChange(next)}>
      <DialogContent className={cn('max-w-xl', className)}>
        <form onSubmit={onSubmit} noValidate className="grid gap-5">
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
            {description && <DialogDescription>{description}</DialogDescription>}
          </DialogHeader>
          <div className="grid gap-4">{children}</div>
          {error && (
            <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger-ink">
              {error}
            </p>
          )}
          <DialogFooter>
            <Button onClick={() => onOpenChange(false)} disabled={pending}>
              {t('actions.cancel')}
            </Button>
            <Button type="submit" variant="primary" loading={pending}>
              {submitLabel}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

/** Edit and delete buttons of a table row; deleting asks first and shows the reason when it fails. */
export function RowActions({
  name,
  onEdit,
  onDelete,
  canEdit = true,
}: {
  name: string
  onEdit: () => void
  onDelete: () => Promise<unknown>
  canEdit?: boolean
}) {
  const { t } = useTranslation('rates')
  const [confirming, setConfirming] = useState(false)
  if (!canEdit) return null
  return (
    <div className="flex justify-end gap-1">
      <Button variant="ghost" size="icon-sm" aria-label={t('crud.edit', { name })} onClick={onEdit}>
        <Pencil aria-hidden />
      </Button>
      <Button variant="ghost" size="icon-sm" aria-label={t('crud.delete', { name })} onClick={() => setConfirming(true)}>
        <Trash2 aria-hidden />
      </Button>
      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title={t('crud.deleteTitle', { name })}
        description={t('crud.deleteHint')}
        confirmLabel={t('actions.delete', { ns: 'common' })}
        onConfirm={onDelete}
      />
    </div>
  )
}

interface FieldProps<T extends FieldValues, N extends FieldPath<T>> {
  control: Control<T>
  name: N
  label: string
  description?: string
  className?: string
}

export function TextField<T extends FieldValues, N extends FieldPath<T>>({
  inputMode,
  placeholder,
  ...props
}: FieldProps<T, N> & { inputMode?: 'text' | 'decimal' | 'numeric'; placeholder?: string }) {
  return (
    <FormField
      {...props}
      render={({ field, ...a11y }) => (
        <Input {...field} {...a11y} inputMode={inputMode} placeholder={placeholder} autoComplete="off" />
      )}
    />
  )
}

export function MoneyField<T extends FieldValues, N extends FieldPath<T>>({
  currency = 'COP',
  ...props
}: FieldProps<T, N> & { currency?: string }) {
  return (
    <FormField
      {...props}
      render={({ field, ...a11y }) => (
        <MoneyInput
          id={a11y.id}
          aria-invalid={a11y['aria-invalid']}
          aria-describedby={a11y['aria-describedby']}
          name={field.name}
          value={field.value ?? ''}
          onChange={field.onChange}
          onBlur={field.onBlur}
          currency={currency}
        />
      )}
    />
  )
}

export function SelectField<T extends FieldValues, N extends FieldPath<T>>({
  options,
  placeholder,
  onValueChange,
  ...props
}: FieldProps<T, N> & {
  options: { value: string; label: string }[]
  placeholder?: string
  /** Called after the form value changes (e.g. to reset dependent fields). */
  onValueChange?: (value: string) => void
}) {
  return (
    <FormField
      {...props}
      render={({ field, id, ...a11y }) => (
        <Select
          name={field.name}
          value={field.value ?? ''}
          onValueChange={(value) => {
            field.onChange(value)
            onValueChange?.(value)
          }}
        >
          <SelectTrigger id={id} {...a11y} onBlur={field.onBlur}>
            <SelectValue placeholder={placeholder} />
          </SelectTrigger>
          <SelectContent>
            {options.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}
    />
  )
}

export function SwitchField<T extends FieldValues, N extends FieldPath<T>>({
  control,
  name,
  label,
  description,
  className,
}: FieldProps<T, N>) {
  const id = useId()
  return (
    <Controller
      control={control}
      name={name}
      render={({ field }) => (
        <div className={cn('flex items-start gap-3', className)}>
          <Switch
            id={id}
            name={field.name}
            checked={Boolean(field.value)}
            onCheckedChange={field.onChange}
            aria-describedby={description ? `${id}-description` : undefined}
            className="mt-0.5"
          />
          <div className="grid gap-0.5">
            <Label htmlFor={id}>{label}</Label>
            {description && (
              <p id={`${id}-description`} className="text-xs text-muted">
                {description}
              </p>
            )}
          </div>
        </div>
      )}
    />
  )
}

/** Optional calendar day (`YYYY-MM-DD` or null) with a button to clear it. */
export function DateField<T extends FieldValues, N extends FieldPath<T>>({
  min,
  clearable = true,
  ...props
}: FieldProps<T, N> & { min?: string | null; clearable?: boolean }) {
  const { t } = useTranslation('rates')
  return (
    <FormField
      {...props}
      render={({ field, id, ...a11y }) => (
        <div className="flex items-center gap-1">
          <DatePicker
            id={id}
            value={field.value ?? null}
            onChange={field.onChange}
            min={min ?? undefined}
            aria-invalid={a11y['aria-invalid']}
            placeholder={t('fields.anyDate')}
            className="flex-1"
          />
          {clearable && field.value && (
            <Button variant="ghost" size="icon-sm" aria-label={t('fields.clearDate')} onClick={() => field.onChange(null)}>
              <X aria-hidden />
            </Button>
          )}
        </div>
      )}
    />
  )
}

export interface ChoiceOption {
  value: string
  label: string
  hint?: string
  /** Color bar of a room type. */
  color?: string
}

/** One choice among a few, shown as radio buttons in a row. */
export function RadioField<T extends FieldValues, N extends FieldPath<T>>({
  control,
  name,
  label,
  options,
  className,
  onValueChange,
}: FieldProps<T, N> & { options: ChoiceOption[]; onValueChange?: (value: string) => void }) {
  const id = useId()
  return (
    <Controller
      control={control}
      name={name}
      render={({ field }) => (
        <fieldset className={cn('grid gap-2', className)}>
          <legend id={`${id}-legend`} className="mb-2 text-[13px] leading-5 font-semibold text-fg">
            {label}
          </legend>
          <RadioGroup
            name={field.name}
            value={field.value}
            onValueChange={(value) => {
              field.onChange(value)
              onValueChange?.(value)
            }}
            aria-labelledby={`${id}-legend`}
            className="flex flex-wrap gap-x-5 gap-y-2"
          >
            {options.map((option) => (
              <div key={option.value} className="flex items-center gap-2">
                <RadioGroupItem id={`${id}-${option.value}`} value={option.value} />
                <Label htmlFor={`${id}-${option.value}`} className="font-medium">
                  {option.label}
                </Label>
              </div>
            ))}
          </RadioGroup>
        </fieldset>
      )}
    />
  )
}

/** Several values from a list of checkboxes (`string[]`); `emptyHint` explains what "none checked" means. */
export function CheckboxGroupField<T extends FieldValues, N extends FieldPath<T>>({
  control,
  name,
  label,
  description,
  options,
  emptyHint,
  className,
}: FieldProps<T, N> & { options: ChoiceOption[]; emptyHint?: string }) {
  const id = useId()
  return (
    <Controller
      control={control}
      name={name}
      render={({ field, fieldState }) => {
        const selected: string[] = field.value ?? []
        const toggle = (value: string, checked: boolean) =>
          field.onChange(
            options.map((option) => option.value).filter((item) => (item === value ? checked : selected.includes(item))),
          )
        return (
          <fieldset className={cn('grid gap-2', className)} aria-describedby={description ? `${id}-description` : undefined}>
            <legend className="mb-1 text-[13px] leading-5 font-semibold text-fg">{label}</legend>
            {description && (
              <p id={`${id}-description`} className="-mt-1 text-xs text-muted">
                {description}
              </p>
            )}
            <div className="grid gap-x-4 gap-y-2 sm:grid-cols-2">
              {options.map((option) => (
                <div key={option.value} className="flex items-start gap-2.5">
                  <Checkbox
                    id={`${id}-${option.value}`}
                    name={`${field.name}-${option.value}`}
                    checked={selected.includes(option.value)}
                    onCheckedChange={(value) => toggle(option.value, value === true)}
                    className="mt-0.5"
                  />
                  {option.color && <span aria-hidden className="mt-0.5 h-4 w-1 shrink-0 rounded-full" style={{ background: option.color }} />}
                  <div className="grid">
                    <label htmlFor={`${id}-${option.value}`} className="text-sm text-fg">
                      {option.label}
                    </label>
                    {option.hint && <span className="text-xs text-muted">{option.hint}</span>}
                  </div>
                </div>
              ))}
            </div>
            {selected.length === 0 && emptyHint && <p className="text-xs text-muted">{emptyHint}</p>}
            {fieldState.error?.message && (
              <FieldError message={fieldState.error.message} />
            )}
          </fieldset>
        )
      }}
    />
  )
}

function FieldError({ message }: { message: string }) {
  const { t, i18n } = useTranslation()
  return (
    <p className="text-xs font-medium text-danger-ink" aria-live="polite">
      {i18n.exists(message) ? t(message) : message}
    </p>
  )
}
