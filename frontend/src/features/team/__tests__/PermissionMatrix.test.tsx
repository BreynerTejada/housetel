import { screen } from '@testing-library/react'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '@/test/render'
import type { PermissionModule } from '../api'
import { PermissionMatrix } from '../components/PermissionMatrix'

const catalog: PermissionModule[] = [
  {
    code: 'bookings',
    label_es: 'Reservas',
    label_en: 'Reservations',
    permissions: [
      { code: 'bookings.view', label_es: 'Ver reservas', label_en: 'View reservations' },
      { code: 'bookings.manage', label_es: 'Crear y modificar reservas', label_en: 'Create and modify reservations' },
      { code: 'bookings.cancel', label_es: 'Cancelar reservas', label_en: 'Cancel reservations' },
    ],
  },
  {
    code: 'finance',
    label_es: 'Finanzas y caja',
    label_en: 'Finance & cashier',
    permissions: [
      { code: 'finance.view', label_es: 'Ver folios y pagos', label_en: 'View folios and payments' },
      { code: 'finance.refund', label_es: 'Reembolsar pagos', label_en: 'Refund payments' },
    ],
  },
]

function Harness({
  initial = [],
  onChange = vi.fn(),
  canGrant,
  readOnly,
}: {
  initial?: string[]
  onChange?: (value: string[]) => void
  canGrant?: (code: string) => boolean
  readOnly?: boolean
}) {
  const [value, setValue] = useState(initial)
  return (
    <PermissionMatrix
      catalog={catalog}
      value={value}
      readOnly={readOnly}
      canGrant={canGrant}
      onChange={(next) => {
        setValue(next)
        onChange(next)
      }}
    />
  )
}

describe('PermissionMatrix', () => {
  it('selects a whole module at once and shows a partial selection', async () => {
    const onChange = vi.fn()
    const { user } = renderWithProviders(<Harness onChange={onChange} />)

    const module = screen.getByRole('checkbox', { name: 'Todos los permisos de Reservas' })
    await user.click(module)

    expect(onChange).toHaveBeenLastCalledWith(['bookings.cancel', 'bookings.manage', 'bookings.view'])
    expect(module).toHaveAttribute('aria-checked', 'true')

    await user.click(screen.getByRole('checkbox', { name: /Cancelar reservas/ }))

    expect(onChange).toHaveBeenLastCalledWith(['bookings.manage', 'bookings.view'])
    expect(module).toHaveAttribute('aria-checked', 'mixed')
    expect(screen.getByText('2 de 3')).toBeInTheDocument()
  })

  it('shows pattern grants as checked and expands them when one permission is removed', async () => {
    const onChange = vi.fn()
    const { user } = renderWithProviders(<Harness initial={['bookings.*', 'finance.view']} onChange={onChange} />)

    expect(screen.getByRole('checkbox', { name: /Cancelar reservas/ })).toHaveAttribute('aria-checked', 'true')
    await user.click(screen.getByRole('checkbox', { name: /Cancelar reservas/ }))

    expect(onChange).toHaveBeenLastCalledWith(['bookings.manage', 'bookings.view', 'finance.view'])
  })

  it('never offers a permission the user cannot grant', async () => {
    const onChange = vi.fn()
    const { user } = renderWithProviders(
      <Harness onChange={onChange} canGrant={(code) => code !== 'finance.refund'} />,
    )

    expect(screen.getByRole('checkbox', { name: /Reembolsar pagos/ })).toBeDisabled()
    await user.click(screen.getByRole('checkbox', { name: 'Todos los permisos de Finanzas y caja' }))

    expect(onChange).toHaveBeenLastCalledWith(['finance.view'])
  })

  it('is read-only for system roles', () => {
    renderWithProviders(<Harness initial={['*']} readOnly />)
    for (const checkbox of screen.getAllByRole('checkbox')) {
      expect(checkbox).toBeDisabled()
      expect(checkbox).toHaveAttribute('aria-checked', 'true')
    }
  })
})
