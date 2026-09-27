import { screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useSession } from '@/lib/session'
import { auroraProperty } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import type { CustomFieldDefinition } from '../api'
import { CreateRoomDialog } from '../components/CreateRoomDialog'
import { makeRoom, minibarField, standardType } from './fixtures'

const ROOMS = '/api/v1/inventory/rooms/'
const FIELDS = '/api/v1/inventory/custom-fields/'

/** A room field the hotel made mandatory without a default value: a new room cannot exist without it. */
const safeCodeField: CustomFieldDefinition = {
  ...minibarField,
  id: 'cf-safe',
  key: 'safe_code',
  label: { es: 'Código de la caja fuerte', en: 'Safe code' },
  field_type: 'text',
  required: true,
  default_value: null,
}

beforeEach(() => {
  document.cookie = 'csrftoken=t; path=/'
  useSession.setState({ propertyId: auroraProperty.id, loggedOut: false })
})

function renderDialog() {
  return renderWithProviders(<CreateRoomDialog open onOpenChange={vi.fn()} roomTypes={[standardType]} />, {
    route: '/app/settings/rooms',
    routes: [{ path: '/app/settings/rooms/:roomId', element: <p>editor</p> }],
  })
}

describe('CreateRoomDialog', () => {
  it('asks for the mandatory room fields that have no default and sends them', async () => {
    const bodies: unknown[] = []
    server.use(
      http.get(FIELDS, () => HttpResponse.json([minibarField, safeCodeField])),
      http.post(ROOMS, async ({ request }) => {
        bodies.push(await request.json())
        return HttpResponse.json(makeRoom({ id: 'r-new', number: '401' }), { status: 201 })
      }),
    )
    const { user, router } = renderDialog()

    const dialog = await screen.findByRole('dialog')
    await user.type(within(dialog).getByRole('textbox', { name: 'Número' }), '401')
    const safe = await within(dialog).findByRole('textbox', { name: /Código de la caja fuerte/ })
    expect(within(dialog).queryByText('Minibar surtido')).not.toBeInTheDocument() // has a default
    await user.type(safe, '1234')
    await user.click(within(dialog).getByRole('button', { name: 'Crear y editar' }))

    await screen.findByText('editor')
    expect(bodies).toEqual([
      { room_type: standardType.id, number: '401', floor: '4', custom_values: { safe_code: '1234' } },
    ])
    expect(router.state.location.pathname).toBe('/app/settings/rooms/r-new')
  })

  it('shows the errors the server gives for fields other than the number', async () => {
    server.use(
      http.get(FIELDS, () => HttpResponse.json([])),
      http.post(ROOMS, () =>
        HttpResponse.json(
          {
            detail: 'La categoría pertenece a otra propiedad',
            code: 'validation_error',
            fields: { room_type: ['La categoría pertenece a otra propiedad'] },
          },
          { status: 400 },
        ),
      ),
    )
    const { user } = renderDialog()

    const dialog = await screen.findByRole('dialog')
    await user.type(within(dialog).getByRole('textbox', { name: 'Número' }), '401')
    await user.click(within(dialog).getByRole('button', { name: 'Crear y editar' }))

    expect(await within(dialog).findByRole('alert')).toHaveTextContent('La categoría pertenece a otra propiedad')
  })
})
