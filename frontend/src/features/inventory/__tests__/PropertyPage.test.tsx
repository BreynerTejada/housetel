import { screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import { useSession } from '@/lib/session'
import { auroraProperty, makeMe, mockMe } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import type { PropertyProfile } from '../api'
import PropertyPage from '../pages/PropertyPage'
import { amenities } from './fixtures'

const URL = '/api/v1/inventory/property/'

const profile: PropertyProfile = {
  id: auroraProperty.id,
  name: 'Hotel Casa Aurora',
  slug: 'casa-aurora',
  property_type: 'boutique',
  status: 'active',
  timezone: 'America/Bogota',
  currency: 'COP',
  business_date: '2026-09-25',
  marketplace_listed: true,
  description: { es: 'Casa colonial', en: 'Colonial house' },
  address: 'Calle del Cuartel #36-77',
  city: 'Cartagena',
  department: 'Bolívar',
  country: 'CO',
  latitude: '10.423600',
  longitude: '-75.551800',
  phone: '+57 605 660 1234',
  email: 'reservas@casaaurora.co',
  website: 'https://casaaurora.co',
  rnt_number: 'RNT 98765',
  nit: '901234567-1',
  legal_name: 'Casa Aurora Hoteles S.A.S.',
  star_rating: 4,
  check_in_time: '15:00',
  check_out_time: '12:00',
  default_language: 'es',
  languages: ['es', 'en'],
  house_rules: { es: 'Silencio desde las 22:00' },
  policies: { pets_allowed: false, smoking_allowed: false, children_allowed: true, events_allowed: true, min_checkin_age: 18 },
  amenities: ['wifi'],
  branding: { primary_color: '#B4583B', logo: '' },
}

function serve(patched: unknown[] = [], respond: () => Response = () => HttpResponse.json(profile)) {
  server.use(
    http.get(URL, () => HttpResponse.json(profile)),
    http.get('/api/v1/inventory/amenities/', () => HttpResponse.json(amenities)),
    http.get('/api/v1/inventory/property/photos/', () => HttpResponse.json([])),
    http.patch(URL, async ({ request }) => {
      patched.push(await request.json())
      return respond()
    }),
  )
}

beforeEach(() => {
  document.cookie = 'csrftoken=t; path=/'
  useSession.setState({ propertyId: auroraProperty.id, loggedOut: false })
  mockMe(makeMe())
})

describe('PropertyPage', () => {
  it('saves the legal data and the schedule', async () => {
    const patched: unknown[] = []
    serve(patched)
    const { user } = renderWithProviders(<PropertyPage />, { route: '/app/settings/property' })

    const nit = await screen.findByRole('textbox', { name: 'NIT' })
    expect(nit).toHaveValue('901234567-1')
    await user.clear(nit)
    await user.type(nit, '900123456-7')
    const checkIn = screen.getByLabelText('Check-in desde')
    await user.clear(checkIn)
    await user.type(checkIn, '14:00')
    await user.click(screen.getByRole('switch', { name: 'Se aceptan mascotas' }))
    await user.click(screen.getByRole('button', { name: 'Guardar cambios' }))

    await screen.findByText('Perfil guardado')
    expect(patched[0]).toMatchObject({
      nit: '900123456-7',
      check_in_time: '14:00',
      policies: { pets_allowed: true },
    })
  })

  it('shows the field errors the server sends back', async () => {
    serve([], () =>
      HttpResponse.json(
        { detail: 'NIT inválido (ej. 900123456-7)', code: 'validation_error', fields: { nit: ['NIT inválido (ej. 900123456-7)'] } },
        { status: 400 },
      ),
    )
    const { user } = renderWithProviders(<PropertyPage />, { route: '/app/settings/property' })
    const nit = await screen.findByRole('textbox', { name: 'NIT' })
    await user.clear(nit)
    await user.type(nit, 'abc')
    await user.click(screen.getByRole('button', { name: 'Guardar cambios' }))

    expect(await screen.findAllByText('NIT inválido (ej. 900123456-7)')).not.toHaveLength(0)
    expect(nit).toHaveAttribute('aria-invalid', 'true')
  })

  it('shows nested server errors (brand color, policies) as their message, next to their field', async () => {
    serve([], () =>
      HttpResponse.json(
        {
          detail: 'Color inválido (#RRGGBB)',
          code: 'validation_error',
          fields: {
            branding: { primary_color: ['Color inválido (#RRGGBB)'] },
            policies: { min_checkin_age: ['Asegúrese de que este valor es menor o igual a 99.'] },
          },
        },
        { status: 400 },
      ),
    )
    const { user } = renderWithProviders(<PropertyPage />, { route: '/app/settings/property' })
    const hex = await screen.findByRole('textbox', { name: 'Color en hexadecimal' })
    await user.clear(hex)
    await user.type(hex, '#12')
    await user.click(screen.getByRole('button', { name: 'Guardar cambios' }))

    const brand = screen.getByRole('region', { name: 'Marca' })
    expect(await within(brand).findByText('Color inválido (#RRGGBB)')).toBeInTheDocument()
    const rules = screen.getByRole('region', { name: 'Reglas y políticas' })
    expect(within(rules).getByText('Asegúrese de que este valor es menor o igual a 99.')).toBeInTheDocument()
    expect(screen.queryByText(/object Object/)).not.toBeInTheDocument()
    expect(hex).toHaveAttribute('aria-invalid', 'true')
  })

  it('shows errors of the bilingual texts next to them', async () => {
    serve([], () =>
      HttpResponse.json(
        { detail: 'Máximo 4000 caracteres', code: 'validation_error', fields: { house_rules: ['Máximo 4000 caracteres'] } },
        { status: 400 },
      ),
    )
    const { user } = renderWithProviders(<PropertyPage />, { route: '/app/settings/property' })
    const rules = await screen.findByRole('group', { name: 'Reglas de la casa' })
    await user.type(within(rules).getByRole('textbox', { name: /español/ }), ' Sin fiestas.')
    await user.click(screen.getByRole('button', { name: 'Guardar cambios' }))

    expect(await within(rules).findByText('Máximo 4000 caracteres')).toBeInTheDocument()
  })
})
