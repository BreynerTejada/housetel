import { zodResolver } from '@hookform/resolvers/zod'
import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useForm } from 'react-hook-form'
import { describe, expect, it, vi } from 'vitest'
import { z } from 'zod'
import { ErrorState } from '@/components/ErrorState'
import { FormField } from '@/components/FormField'
import { StatusBadge } from '@/components/StatusBadge'
import { Input } from '@/components/ui/input'
import { ApiError } from '@/lib/api'
import i18n from '@/lib/i18n'

describe('StatusBadge', () => {
  it('names reservation states in the UI language', async () => {
    const { rerender } = render(<StatusBadge kind="reservation" status="checked_in" />)
    expect(screen.getByText('En casa')).toBeInTheDocument()

    // react-i18next re-renders mounted components on languageChanged: let React flush that update.
    await act(() => i18n.changeLanguage('en'))
    rerender(<StatusBadge kind="reservation" status="checked_in" />)
    expect(screen.getByText('In house')).toBeInTheDocument()
  })

  it('uses the room-state colors of the design system', () => {
    render(
      <>
        <StatusBadge kind="room" status="clean" />
        <StatusBadge kind="room" status="dirty" />
        <StatusBadge kind="room" status="out_of_service" />
      </>,
    )
    expect(screen.getByText('Limpia').closest('[data-status]')).toHaveAttribute('data-tone', 'success')
    expect(screen.getByText('Sucia').closest('[data-status]')).toHaveAttribute('data-tone', 'warning')
    expect(screen.getByText('Fuera de servicio').closest('[data-status]')).toHaveAttribute('data-tone', 'stone')
  })

  it('shows unknown states as they come instead of breaking', () => {
    render(<StatusBadge kind="payment" status="chargeback" />)
    expect(screen.getByText('chargeback').closest('[data-status]')).toHaveAttribute('data-tone', 'neutral')
  })
})

const schema = z.object({ email: z.string().min(1, 'validation.required').email('validation.email') })

function EmailForm({ onValid }: { onValid: (values: z.infer<typeof schema>) => void }) {
  const form = useForm({ resolver: zodResolver(schema), defaultValues: { email: '' } })
  return (
    <form onSubmit={form.handleSubmit(onValid)} noValidate>
      <FormField
        control={form.control}
        name="email"
        label="Correo electrónico"
        description="El de tu cuenta de Housetel."
        render={({ field, ...a11y }) => <Input type="email" {...field} {...a11y} />}
      />
      <button type="submit">Enviar</button>
    </form>
  )
}

describe('FormField', () => {
  it('links the label and description to the control', () => {
    render(<EmailForm onValid={vi.fn()} />)
    const input = screen.getByLabelText('Correo electrónico')
    expect(input).toHaveAccessibleDescription('El de tu cuenta de Housetel.')
  })

  it('shows the translated validation message and marks the control invalid', async () => {
    const onValid = vi.fn()
    render(<EmailForm onValid={onValid} />)

    await userEvent.click(screen.getByRole('button', { name: 'Enviar' }))

    const input = screen.getByLabelText('Correo electrónico')
    expect(await screen.findByText('Este campo es obligatorio')).toBeInTheDocument()
    expect(input).toHaveAttribute('aria-invalid', 'true')
    expect(input).toHaveAccessibleDescription(expect.stringContaining('Este campo es obligatorio'))
    expect(onValid).not.toHaveBeenCalled()

    await userEvent.type(input, 'no-es-correo')
    await userEvent.click(screen.getByRole('button', { name: 'Enviar' }))
    expect(await screen.findByText('Escribe un correo válido')).toBeInTheDocument()
  })
})

describe('ErrorState', () => {
  it('explains the failure and lets the user retry', async () => {
    const onRetry = vi.fn()
    render(<ErrorState error={new ApiError(0, 'network_error', 'Failed to fetch')} onRetry={onRetry} />)

    expect(screen.getByText('No pudimos cargar esta información')).toBeInTheDocument()
    expect(screen.getByText('Sin conexión con el servidor. Revisa tu red e inténtalo de nuevo.')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })
})
