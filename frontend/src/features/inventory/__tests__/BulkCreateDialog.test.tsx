import { screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useSession } from '@/lib/session'
import { auroraProperty } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import { BulkCreateDialog } from '../components/BulkCreateDialog'
import { dormType, makeRoom, standardType } from './fixtures'

const URL = '/api/v1/inventory/rooms/bulk-create/'

beforeEach(() => {
  document.cookie = 'csrftoken=t; path=/'
  useSession.setState({ propertyId: auroraProperty.id, loggedOut: false })
})

function renderDialog(onOpenChange = vi.fn()) {
  const utils = renderWithProviders(
    <BulkCreateDialog open onOpenChange={onOpenChange} roomTypes={[standardType, dormType]} defaultRoomTypeId={standardType.id} />,
  )
  return { ...utils, onOpenChange }
}

describe('BulkCreateDialog', () => {
  it('previews the rooms a range will create and where they go', async () => {
    const { user } = renderDialog()
    await user.type(screen.getByRole('textbox', { name: 'Números' }), '101-103,105,201')

    const preview = screen.getByRole('list', { name: 'Vista previa' })
    expect(within(preview).getAllByRole('listitem').map((item) => item.textContent)).toEqual(['101', '102', '103', '105', '201'])
    expect(screen.getByText('5 habitaciones · pisos 1 y 2')).toBeInTheDocument()
  })

  it('explains an invalid range and does not let it be sent', async () => {
    const { user } = renderDialog()
    await user.type(screen.getByRole('textbox', { name: 'Números' }), '110-101')

    expect(screen.getByText('El rango 110-101 termina antes de empezar.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Crear habitaciones' })).toBeDisabled()
  })

  it('flags numbers repeated in the text before sending', async () => {
    const { user } = renderDialog()
    await user.type(screen.getByRole('textbox', { name: 'Números' }), '101-103,102')
    expect(screen.getByText('Se repite: 102')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Crear habitaciones' })).toBeDisabled()
  })

  it('sends the category, the numbers and an automatic floor, and marks numbers that already exist', async () => {
    const bodies: unknown[] = []
    server.use(
      http.post(URL, async ({ request }) => {
        bodies.push(await request.json())
        return HttpResponse.json(
          { detail: 'Estos números ya existen o se repiten: 102', code: 'duplicate_room_numbers', duplicates: ['102'] },
          { status: 400 },
        )
      }),
    )
    const { user } = renderDialog()
    await user.type(screen.getByRole('textbox', { name: 'Números' }), '101-103')
    await user.click(screen.getByRole('button', { name: 'Crear habitaciones' }))

    expect(await screen.findByText('Ya existen: 102')).toBeInTheDocument()
    expect(bodies).toEqual([{ room_type: standardType.id, numbers: '101-103', floor: null, building: '', beds_per_room: null }])
    const preview = screen.getByRole('list', { name: 'Vista previa' })
    expect(within(preview).getByText('102').closest('li')).toHaveAttribute('data-duplicate', 'true')
  })

  it('creates the rooms and closes', async () => {
    server.use(
      http.post(URL, () =>
        HttpResponse.json(
          { count: 2, rooms: [makeRoom({ id: 'r1', number: '401' }), makeRoom({ id: 'r2', number: '402' })] },
          { status: 201 },
        ),
      ),
    )
    const { user, onOpenChange } = renderDialog()
    await user.type(screen.getByRole('textbox', { name: 'Números' }), '401-402')
    await user.type(screen.getByRole('textbox', { name: 'Piso' }), '4')
    await user.click(screen.getByRole('button', { name: 'Crear habitaciones' }))

    expect(await screen.findByText('Se crearon 2 habitaciones')).toBeInTheDocument()
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })
})
