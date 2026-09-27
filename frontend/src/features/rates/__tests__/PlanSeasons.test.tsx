import { act, screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import i18n from '@/lib/i18n'
import { useSession } from '@/lib/session'
import { auroraMembership, auroraProperty, makeMe, mockMe } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import PlansPage from '../pages/PlansPage'
import { mockPlansApi } from './fixtures'

function renderSeasons() {
  return renderWithProviders(<PlansPage />, { route: '/app/rates/plans?tab=seasons', path: '/app/rates/plans' })
}

beforeEach(() => {
  document.cookie = 'csrftoken=t; path=/'
  useSession.setState({ propertyId: auroraProperty.id, loggedOut: false })
  mockMe(makeMe())
})

describe('seasons', () => {
  it('lists each season and paints its nights on the calendar of the business year', async () => {
    mockPlansApi()
    renderSeasons()

    const item = await screen.findByRole('button', { name: /^Alta fin de año/ })
    expect(item).toHaveTextContent('15 dic 2026 – 15 ene 2027')
    expect(item).toHaveTextContent('Prioridad 10')

    const calendar = screen.getByRole('region', { name: 'Calendario 2026' })
    expect(within(calendar).getByRole('cell', { name: 'dom 20 dic · Alta fin de año' })).toBeInTheDocument()
    expect(within(calendar).getByRole('cell', { name: 'lun 14 dic' })).toBeInTheDocument()
    expect(await within(calendar).findByRole('cell', { name: 'mar 8 dic · Festivo: Inmaculada Concepción' })).toBeInTheDocument()
  })

  it('asks for the holidays in the language on screen and follows a language change', async () => {
    mockPlansApi()
    const asked: (string | null)[] = []
    server.use(
      http.get('/api/v1/rates/holidays/', ({ request }) => {
        const lang = new URL(request.url).searchParams.get('lang')
        asked.push(lang)
        return HttpResponse.json([{ date: '2026-12-08', name: lang === 'en' ? 'Immaculate Conception' : 'Inmaculada Concepción' }])
      }),
    )
    renderSeasons()
    const calendar = await screen.findByRole('region', { name: 'Calendario 2026' })
    expect(await within(calendar).findByRole('cell', { name: /Festivo: Inmaculada Concepción/ })).toBeInTheDocument()

    await act(() => i18n.changeLanguage('en'))
    expect(await screen.findByRole('cell', { name: /Immaculate Conception/ })).toBeInTheDocument()
    expect(asked).toEqual(['es', 'en'])
  })

  it('moves the calendar to another year', async () => {
    mockPlansApi()
    const { user } = renderSeasons()

    await screen.findByRole('region', { name: 'Calendario 2026' })
    await user.click(screen.getByRole('button', { name: 'Año siguiente' }))
    const calendar = screen.getByRole('region', { name: 'Calendario 2027' })
    expect(within(calendar).getByRole('cell', { name: 'vie 15 ene · Alta fin de año' })).toBeInTheDocument()
    expect(within(calendar).getByRole('cell', { name: 'sáb 16 ene' })).toBeInTheDocument()
  })

  it('creates a season that starts on the business date', async () => {
    const writes = mockPlansApi()
    const { user } = renderSeasons()

    await user.click(await screen.findByRole('button', { name: 'Nueva temporada' }))
    const dialog = await screen.findByRole('dialog', { name: 'Nueva temporada' })
    await user.type(within(dialog).getByLabelText('Nombre'), 'Puente festivo')
    await user.click(within(dialog).getByRole('button', { name: /Última noche/ }))
    await user.click(await screen.findByRole('button', { name: /12 de octubre de 2026/ }))
    await user.clear(within(dialog).getByLabelText('Prioridad'))
    await user.type(within(dialog).getByLabelText('Prioridad'), '5')
    await user.click(within(dialog).getByRole('radio', { name: 'Pizarra' }))
    await user.click(within(dialog).getByRole('button', { name: 'Crear temporada' }))

    await waitFor(() => expect(writes).toHaveLength(1))
    expect(writes[0]).toEqual({
      method: 'POST',
      path: 'seasons',
      body: { name: 'Puente festivo', start_date: '2026-09-25', end_date: '2026-10-12', priority: 5, color: '#4E6C88' },
    })
    expect(await screen.findByText('Temporada creada')).toBeInTheDocument()
  })

  it('prices a category for the selected season', async () => {
    const writes = mockPlansApi()
    const { user } = renderSeasons()

    const table = await screen.findByRole('table', { name: 'Precios de Alta fin de año en Tarifa flexible' })
    const standard = within(table).getByRole('row', { name: /Estándar/ })
    expect(within(standard).getByText(/^\$\s416\.000$/)).toBeInTheDocument()
    expect(within(standard).getByText('+30 %')).toBeInTheDocument()

    await user.click(within(table).getByRole('button', { name: 'Poner precio de temporada a Suite Vista al Mar' }))
    const dialog = await screen.findByRole('dialog', { name: 'Precio de temporada · Suite Vista al Mar' })
    await user.type(within(dialog).getByLabelText('Precio por noche'), '845000')
    await user.click(within(dialog).getByRole('button', { name: 'Guardar precio' }))

    await waitFor(() => expect(writes).toHaveLength(1))
    expect(writes[0]).toEqual({
      method: 'POST',
      path: 'season-rates',
      body: { season: 'season-high', room_type: 'rt-ste', rate_plan: 'plan-flex', price: '845000', dow_adjustments: {} },
    })
  })

  it('computes the season prices from the default prices', async () => {
    const writes = mockPlansApi()
    const { user } = renderSeasons()

    await screen.findByRole('table', { name: /Precios de Alta fin de año/ })
    await user.type(screen.getByLabelText('Sobre el precio por defecto (%)'), '25')
    await user.click(screen.getByRole('button', { name: 'Calcular precios' }))

    await waitFor(() => expect(writes).toHaveLength(1))
    // Estándar: 320.000 × 1,25 = 400.000 with its weekday adjustments; the suite has no default price yet
    expect(writes[0].body).toEqual({
      season: 'season-high',
      room_type: 'rt-dbl',
      rate_plan: 'plan-flex',
      price: '400000',
      dow_adjustments: { fri: 15, sat: 15 },
    })
    expect(await screen.findByText(/Suite Vista al Mar no tiene precio por defecto/)).toBeInTheDocument()
  })

  it('lets front desk see the seasons without editing them', async () => {
    mockMe(makeMe({ memberships: [auroraMembership(['rates.view'], 'front_desk')] }))
    mockPlansApi()
    renderSeasons()

    await screen.findByRole('table', { name: /Precios de Alta fin de año/ })
    expect(screen.queryByRole('button', { name: 'Nueva temporada' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Poner precio|Editar|Calcular precios/ })).not.toBeInTheDocument()
  })
})
