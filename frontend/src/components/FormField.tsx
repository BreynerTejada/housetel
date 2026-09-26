import { useId, type ReactElement, type ReactNode } from 'react'
import {
  Controller,
  type Control,
  type ControllerFieldState,
  type ControllerRenderProps,
  type FieldPath,
  type FieldValues,
} from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import { Label } from './ui/label'

export interface FieldControlProps<T extends FieldValues, N extends FieldPath<T>> {
  field: ControllerRenderProps<T, N>
  id: string
  'aria-invalid': boolean
  'aria-describedby'?: string
}

interface FormFieldProps<T extends FieldValues, N extends FieldPath<T>> {
  control: Control<T>
  name: N
  label: ReactNode
  description?: ReactNode
  className?: string
  /**
   * Render the control and spread the a11y props on it:
   * `render={({ field, ...a11y }) => <Input {...field} {...a11y} />}`.
   */
  render: (props: FieldControlProps<T, N>, meta: { fieldState: ControllerFieldState }) => ReactElement
}

/**
 * Label + control + description + error for react-hook-form. Validation messages may be i18n keys of
 * the common namespace (`validation.required`) or plain text.
 */
export function FormField<T extends FieldValues, N extends FieldPath<T>>({
  control,
  name,
  label,
  description,
  className,
  render,
}: FormFieldProps<T, N>) {
  const { t, i18n } = useTranslation()
  const id = useId()
  const descriptionId = `${id}-description`
  const errorId = `${id}-error`

  return (
    <Controller
      control={control}
      name={name}
      render={({ field, fieldState }) => {
        const message = fieldState.error?.message
        const describedBy = [description ? descriptionId : null, message ? errorId : null].filter(Boolean).join(' ')
        return (
          <div className={cn('grid gap-1.5', className)}>
            <Label htmlFor={id}>{label}</Label>
            {render(
              { field, id, 'aria-invalid': Boolean(fieldState.error), 'aria-describedby': describedBy || undefined },
              { fieldState },
            )}
            {description && (
              <p id={descriptionId} className="text-xs text-muted">
                {description}
              </p>
            )}
            {message && (
              <p id={errorId} className="text-xs font-medium text-danger-ink" aria-live="polite">
                {i18n.exists(message) ? t(message) : message}
              </p>
            )}
          </div>
        )
      }}
    />
  )
}
