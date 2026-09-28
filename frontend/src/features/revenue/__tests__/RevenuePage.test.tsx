import { screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import { useSession } from '@/lib/session'
import { auroraProperty, makeMe, mockMe } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import RevenuePage from '../pages/RevenuePage'
import { makeRun, makeSummary, mockRevenueApi, OPTIONS, RULES } from './fixtures'

beforeEach(() => {
  document.cookie = 'csrftoken=t; path=/'
  useSession.setState({ propertyId: auroraProperty.id, loggedOut: false })
  localStorage.clear()
  mockMe(makeMe())
})

describe('revenue page', () => {
  it('runs the rules now and refreshes what is pending', async () => {
    const log = mockRevenueApi()
    let runs = 0
    server.use(
      http.post('/api/v1/revenue/run-now/', () => {
        runs += 1
        return HttpResponse.json(makeRun({ id: 'run-9', trigger: 'manual', recommendations_count: 3 }), { status: 201 })
      }),
    )
    const { user } = renderWithProviders(<RevenuePage />, { route: '/app/revenue' })

    await screen.findByRole('grid', { name: 'Recomendaciones de precio por categoría y noche' })
    const calendarLoads = log.calendarRequests.length
    await user.click(screen.getByRole('button', { name: 'Correr ahora' }))

    expect(await screen.findByText('Corrida lista: 3 recomendaciones pendientes')).toBeInTheDocument()
    expect(runs).toBe(1)
    await waitFor(() => expect(log.calendarRequests.length).toBeGreaterThan(calendarLoads))
  })

  it('says why a run was refused', async () => {
    mockRevenueApi()
    server.use(
      http.post('/api/v1/revenue/run-now/', () =>
        HttpResponse.json({ detail: 'Revenue management está desactivado para esta propiedad', code: 'revenue_disabled' }, { status: 409 }),
      ),
    )
    const { user } = renderWithProviders(<RevenuePage />, { route: '/app/revenue' })

    await user.click(await screen.findByRole('button', { name: 'Correr ahora' }))
    expect(await screen.findByText('Revenue management está desactivado para esta propiedad')).toBeInTheDocument()
  })

  it('warns while revenue management is off and does not offer to run it', async () => {
    mockRevenueApi({ summary: makeSummary({ enabled: false }) })
    renderWithProviders(<RevenuePage />, { route: '/app/revenue' })

    expect(await screen.findByText(/Revenue management está desactivado: las reglas no corren solas/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Correr ahora' })).toBeDisabled()
    expect(screen.getByRole('link', { name: 'Ir a ajustes' })).toHaveAttribute('href', '/app/revenue?tab=settings')
  })

  it('opens the section named in the address and keeps the address in sync', async () => {
    mockRevenueApi()
    server.use(
      http.get('/api/v1/revenue/rules/', () => HttpResponse.json(RULES)),
      http.get('/api/v1/revenue/options/', () => HttpResponse.json(OPTIONS)),
      http.get('/api/v1/revenue/runs/', () => HttpResponse.json({ count: 0, next: null, previous: null, results: [] })),
    )
    const { user, router } = renderWithProviders(<RevenuePage />, { route: '/app/revenue?tab=rules' })

    expect(await screen.findByRole('article', { name: 'Ocupación' })).toBeInTheDocument()
    await user.click(screen.getByRole('tab', { name: 'Historial' }))
    expect(await screen.findByText('Todavía no hay corridas.')).toBeInTheDocument()
    expect(router.state.location.search).toBe('?tab=history')
  })
})
