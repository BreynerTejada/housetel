import { screen, waitFor } from '@testing-library/react'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { ConfirmDialog, DangerConfirmDialog } from '@/components/ConfirmDialog'
import { ApiError } from '@/lib/api'
import { renderWithProviders } from '@/test/render'

function Harness({ onConfirm, danger = false }: { onConfirm: () => unknown; danger?: boolean }) {
  const [open, setOpen] = useState(true)
  return (
    <>
      <p>dialog {open ? 'open' : 'closed'}</p>
      {danger ? (
        <DangerConfirmDialog
          open={open}
          onOpenChange={setOpen}
          title="Reembolsar pago"
          description="El dinero vuelve a la tarjeta del huésped."
          confirmText="350.000"
          confirmLabel="Reembolsar"
          onConfirm={onConfirm}
        />
      ) : (
        <ConfirmDialog
          open={open}
          onOpenChange={setOpen}
          title="Marcar como no show"
          confirmLabel="Marcar no show"
          onConfirm={onConfirm}
        />
      )}
    </>
  )
}

describe('ConfirmDialog', () => {
  it('runs the action and closes once it succeeds', async () => {
    const onConfirm = vi.fn().mockResolvedValue(undefined)
    const { user } = renderWithProviders(<Harness onConfirm={onConfirm} />)

    await user.click(screen.getByRole('button', { name: 'Marcar no show' }))

    expect(onConfirm).toHaveBeenCalledTimes(1)
    expect(await screen.findByText('dialog closed')).toBeInTheDocument()
  })

  it('closes without running the action on cancel', async () => {
    const onConfirm = vi.fn()
    const { user } = renderWithProviders(<Harness onConfirm={onConfirm} />)

    await user.click(screen.getByRole('button', { name: 'Cancelar' }))

    expect(onConfirm).not.toHaveBeenCalled()
    expect(await screen.findByText('dialog closed')).toBeInTheDocument()
  })

  it('stays open and explains the failure when the action fails', async () => {
    const onConfirm = vi.fn().mockRejectedValue(new ApiError(409, 'invalid_state', 'La reserva ya tiene check-in'))
    const { user } = renderWithProviders(<Harness onConfirm={onConfirm} />)

    await user.click(screen.getByRole('button', { name: 'Marcar no show' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('La reserva ya tiene check-in')
    expect(screen.getByText('dialog open')).toBeInTheDocument()
  })
})

describe('DangerConfirmDialog', () => {
  it('keeps the action disabled until the exact text is typed', async () => {
    const onConfirm = vi.fn().mockResolvedValue(undefined)
    const { user } = renderWithProviders(<Harness danger onConfirm={onConfirm} />)
    const confirm = screen.getByRole('button', { name: 'Reembolsar' })
    const input = screen.getByLabelText('Texto de confirmación')

    expect(screen.getByText('350.000', { selector: 'strong' })).toBeInTheDocument()
    expect(confirm).toBeDisabled()

    await user.type(input, '350000')
    expect(confirm).toBeDisabled()

    await user.clear(input)
    await user.type(input, '350.000')
    expect(confirm).toBeEnabled()

    await user.click(confirm)

    expect(onConfirm).toHaveBeenCalledTimes(1)
    await waitFor(() => expect(screen.getByText('dialog closed')).toBeInTheDocument())
  })

  it('does not run the action when Enter is pressed with the wrong text', async () => {
    const onConfirm = vi.fn()
    const { user } = renderWithProviders(<Harness danger onConfirm={onConfirm} />)

    await user.type(screen.getByLabelText('Texto de confirmación'), '35{Enter}')

    expect(onConfirm).not.toHaveBeenCalled()
  })
})
