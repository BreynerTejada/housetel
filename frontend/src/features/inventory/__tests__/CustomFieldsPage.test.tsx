import { screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import { useSession } from '@/lib/session'
import { auroraProperty, makeMe, mockMe } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import CustomFieldsPage from '../pages/CustomFieldsPage'
import { minibarField, orientationField } from './fixtures'

const URL = '/api/v1/inventory/custom-fields/'

beforeEach(() => {
  document.cookie = 'csrftoken=t; path=/'
  useSession.setState({ propertyId: auroraProperty.id, loggedOut: false })
  mockMe(makeMe())
})

describe('CustomFieldsPage', () => {
  it('groups the definitions by what they apply to', async () => {
    server.use(http.get(URL, () => HttpResponse.json([orientationField, minibarField])))
    renderWithProviders(<CustomFieldsPage />, { route: '/app/settings/custom-fields' })

    const categories = await screen.findByRole('region', { name: 'Categorías' })
    expect(within(categories).getByText('Orientación')).toBeInTheDocument()
    expect(within(categories).getByText('Lista · 2 opciones')).toBeInTheDocument()
    const rooms = screen.getByRole('region', { name: 'Habitaciones' })
    expect(within(rooms).getByText('Minibar surtido')).toBeInTheDocument()
  })

  it('keeps numeric option values when only the label changes (so no stored value is dropped)', async () => {
    const numeric = { ...orientationField, id: 'cf-level', key: 'level', options: [{ value: 1, label: { es: 'Uno' } }, { value: 2, label: { es: 'Dos' } }] }
    const bodies: unknown[] = []
    server.use(
      http.get(URL, () => HttpResponse.json([numeric])),
      http.patch(`${URL}cf-level/`, async ({ request }) => {
        bodies.push(await request.json())
        return HttpResponse.json(numeric)
      }),
    )
    const { user } = renderWithProviders(<CustomFieldsPage />, { route: '/app/settings/custom-fields' })

    await user.click(await screen.findByRole('button', { name: 'Editar Orientación' }))
    const dialog = await screen.findByRole('dialog')
    const name = within(dialog).getByRole('textbox', { name: 'Nombre (español)' })
    await user.clear(name)
    await user.type(name, 'Nivel')
    await user.click(within(dialog).getByRole('button', { name: 'Guardar campo' }))

    await screen.findByText('Campo guardado')
    expect(bodies[0]).toMatchObject({ label: { es: 'Nivel' }, options: [{ value: 1 }, { value: 2 }] })
  })

  it('creates a list field: the key follows the label and options are required', async () => {
    const bodies: unknown[] = []
    server.use(
      http.get(URL, () => HttpResponse.json([])),
      http.post(URL, async ({ request }) => {
        bodies.push(await request.json())
        return HttpResponse.json({ ...orientationField, id: 'new' }, { status: 201 })
      }),
    )
    const { user } = renderWithProviders(<CustomFieldsPage />, { route: '/app/settings/custom-fields' })

    await user.click(await screen.findByRole('button', { name: 'Nuevo campo' }))
    const dialog = await screen.findByRole('dialog')
    await user.type(within(dialog).getByRole('textbox', { name: 'Nombre (español)' }), 'Tipo de vista')
    expect(within(dialog).getByRole('textbox', { name: 'Clave' })).toHaveValue('tipo_de_vista')

    await user.click(within(dialog).getByRole('combobox', { name: 'Tipo de dato' }))
    await user.click(await screen.findByRole('option', { name: 'Lista' }))
    expect(within(dialog).getByText('Agrega al menos una opción')).toBeInTheDocument()
    expect(within(dialog).getByRole('button', { name: 'Crear campo' })).toBeDisabled()

    await user.click(within(dialog).getByRole('button', { name: 'Agregar opción' }))
    await user.type(within(dialog).getByRole('textbox', { name: 'Valor de la opción 1' }), 'mar')
    await user.click(within(dialog).getByRole('button', { name: 'Crear campo' }))

    await screen.findByText('Campo creado')
    expect(bodies[0]).toMatchObject({
      applies_to: 'room_type',
      key: 'tipo_de_vista',
      label: { es: 'Tipo de vista' },
      field_type: 'select',
      options: [{ value: 'mar', label: { es: 'mar' } }],
      scope: 'organization',
    })
  })
})
