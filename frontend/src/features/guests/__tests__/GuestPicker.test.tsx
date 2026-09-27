import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { useState } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useSession } from '@/lib/session'
import { makeMe, mockMe } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import type { GuestPickerValue } from '../api'
import { GuestPicker } from '../components/GuestPicker'
import { makeDuplicate, makeGuestSummary, page } from './fixtures'

function Harness({ onChange, initial = null }: { onChange: (value: GuestPickerValue | null) => void; initial?: GuestPickerValue | null }) {
  const [value, setValue] = useState<GuestPickerValue | null>(initial)
  return (
    <GuestPicker
      value={value}
      onChange={(next) => {
        setValue(next)
        onChange(next)
      }}
    />
  )
}

beforeEach(() => {
  useSession.setState({ propertyId: null, loggedOut: false })
  mockMe(makeMe())
  server.use(http.get('/api/v1/guests/guests/lookup/', () => HttpResponse.json([])))
})

describe('GuestPicker', () => {
  it('searches as you type and picks an existing guest', async () => {
    const queries: string[] = []
    server.use(
      http.get('/api/v1/guests/guests/', ({ request }) => {
        queries.push(new URL(request.url).searchParams.get('q') ?? '')
        return HttpResponse.json(page([makeGuestSummary({ is_vip: true })]))
      }),
    )
    const onChange = vi.fn()
    const { user } = renderWithProviders(<Harness onChange={onChange} />)

    await user.type(screen.getByRole('combobox', { name: 'Buscar huésped' }), 'ana pe')

    const option = await screen.findByRole('option', { name: /Ana María Pérez Gómez/ })
    expect(within(option).getByText(/CC 52\.123\.456/)).toBeInTheDocument()
    expect(queries.at(-1)).toBe('ana pe')
    expect(queries).not.toContain('a') // debounced: no request per keystroke
    await user.click(option)

    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ id: 'guest-ana' }))
    expect(screen.getByText('Ana María Pérez Gómez')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cambiar huésped' })).toBeInTheDocument()
  })

  it('creates a new guest inline from what was typed, without saving it', async () => {
    server.use(http.get('/api/v1/guests/guests/', () => HttpResponse.json(page([]))))
    const onChange = vi.fn()
    const { user } = renderWithProviders(<Harness onChange={onChange} />)

    await user.type(screen.getByRole('combobox', { name: 'Buscar huésped' }), 'Laura Ríos')
    await user.click(await screen.findByRole('option', { name: /Crear «Laura Ríos» como huésped nuevo/ }))

    expect(screen.getByRole('textbox', { name: 'Nombres' })).toHaveValue('Laura')
    expect(screen.getByRole('textbox', { name: 'Apellidos' })).toHaveValue('Ríos')
    await user.type(screen.getByRole('textbox', { name: 'Correo' }), 'laura@example.com')
    await user.type(screen.getByRole('textbox', { name: 'Número de documento' }), '1017234567')
    await user.click(screen.getByRole('button', { name: 'Usar estos datos' }))

    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({
        first_name: 'Laura',
        last_name: 'Ríos',
        email: 'laura@example.com',
        document_type: 'CC',
        document_number: '1017234567',
        nationality: 'CO',
      }),
    )
    expect(onChange.mock.lastCall?.[0]).not.toHaveProperty('id')
    expect(screen.getByText('Nuevo')).toBeInTheDocument()
  })

  it('warns about a likely duplicate and can use the existing profile instead', async () => {
    server.use(
      http.get('/api/v1/guests/guests/', () => HttpResponse.json(page([]))),
      http.get('/api/v1/guests/guests/lookup/', ({ request }) => {
        const params = new URL(request.url).searchParams
        return HttpResponse.json(params.get('document_number') === '52123456' ? [makeDuplicate({ id: 'guest-ana', full_name: 'Ana María Pérez Gómez' })] : [])
      }),
    )
    const onChange = vi.fn()
    const { user } = renderWithProviders(<Harness onChange={onChange} />)

    await user.type(screen.getByRole('combobox', { name: 'Buscar huésped' }), 'Ana')
    await user.click(await screen.findByRole('option', { name: /como huésped nuevo/ }))
    await user.type(screen.getByRole('textbox', { name: 'Número de documento' }), '52123456')

    const warning = await screen.findByRole('status', { name: 'Posible duplicado' })
    expect(within(warning).getByText('Ana María Pérez Gómez')).toBeInTheDocument()
    expect(within(warning).getByText('Mismo documento')).toBeInTheDocument()
    await user.click(within(warning).getByRole('button', { name: 'Usar este perfil' }))

    await waitFor(() => expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ id: 'guest-ana' })))
  })

  it('lives inside the consumer form without ever submitting it', async () => {
    server.use(http.get('/api/v1/guests/guests/', () => HttpResponse.json(page([]))))
    const onSubmit = vi.fn((event: { preventDefault: () => void }) => event.preventDefault())
    const onChange = vi.fn()
    const { user } = renderWithProviders(
      <form onSubmit={onSubmit}>
        <Harness onChange={onChange} />
        <button type="submit">Siguiente</button>
      </form>,
    )

    const search = screen.getByRole('combobox', { name: 'Buscar huésped' })
    await user.click(search)
    await user.keyboard('{Enter}') // empty search
    await user.type(search, 'Laura Ríos')
    await user.click(await screen.findByRole('option', { name: /como huésped nuevo/ }))
    await user.type(screen.getByRole('textbox', { name: 'Correo' }), 'laura@example.com{Enter}')

    expect(onSubmit).not.toHaveBeenCalled()
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ first_name: 'Laura', email: 'laura@example.com' }))
  })

  it('lets the user change the chosen guest', async () => {
    server.use(http.get('/api/v1/guests/guests/', () => HttpResponse.json(page([]))))
    const onChange = vi.fn()
    const { user } = renderWithProviders(<Harness onChange={onChange} initial={makeGuestSummary()} />)

    await user.click(screen.getByRole('button', { name: 'Cambiar huésped' }))

    expect(onChange).toHaveBeenLastCalledWith(null)
    expect(screen.getByRole('combobox', { name: 'Buscar huésped' })).toHaveFocus()
  })
})
