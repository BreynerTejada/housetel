import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import { useSession } from '@/lib/session'
import { auroraMembership, auroraProperty, makeMe, mockMe } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import RecommendationsWidget from '../components/RecommendationsWidget'
import { makeRecommendation, makeSummary, STE } from './fixtures'

const UPCOMING = [
  makeRecommendation(),
  makeRecommendation({ id: 'rec-ste-26', room_type: STE, current_price: '650000.00', recommended_price: '748000.00', change_percent: '15.00' }),
  makeRecommendation({ id: 'rec-dbl-28', date: '2026-09-28', recommended_price: '294000.00', change_percent: '-8.00' }),
]

function mockWidgetApi({ summary = makeSummary(), upcoming = UPCOMING } = {}) {
  const log = { listRequests: [] as URL[], approved: [] as string[][] }
  server.use(
    http.get('/api/v1/revenue/recommendations/summary/', () => HttpResponse.json(summary)),
    http.get('/api/v1/revenue/recommendations/', ({ request }) => {
      log.listRequests.push(new URL(request.url))
      return HttpResponse.json({ count: upcoming.length, next: null, previous: null, results: upcoming })
    }),
    http.post('/api/v1/revenue/recommendations/approve/', async ({ request }) => {
      const { ids } = (await request.json()) as { ids: string[] }
      log.approved.push(ids)
      return HttpResponse.json({
        updated: ids.length,
        skipped: [],
        errors: [],
        recommendations: ids.map((id) => makeRecommendation({ id, status: 'applied' })),
      })
    }),
  )
  return log
}

beforeEach(() => {
  document.cookie = 'csrftoken=t; path=/'
  useSession.setState({ propertyId: auroraProperty.id, loggedOut: false })
  mockMe(makeMe())
})

describe('price recommendations widget', () => {
  it('shows the next nights to decide and approves one in a click', async () => {
    const log = mockWidgetApi()
    const { user } = renderWithProviders(<RecommendationsWidget />)

    const widget = await screen.findByRole('region', { name: 'Recomendaciones de precio' })
    expect(await within(widget).findByText('3 por decidir')).toBeInTheDocument()
    expect(await within(widget).findByText('+12 %')).toBeInTheDocument()
    expect(within(widget).getByText('−8 %')).toBeInTheDocument()
    expect(log.listRequests[0].searchParams.get('status')).toBe('pending')
    expect(log.listRequests[0].searchParams.get('start')).toBe('2026-09-25')

    await user.click(within(widget).getByRole('button', { name: 'Aprobar Estándar el sáb 26 sep' }))
    await waitFor(() => expect(log.approved).toEqual([['rec-dbl-26']]))
    expect(await screen.findByText('1 recomendación aprobada y aplicada a la grilla')).toBeInTheDocument()
  })

  it('approves every night it shows at once', async () => {
    const log = mockWidgetApi()
    const { user } = renderWithProviders(<RecommendationsWidget />)

    await user.click(await screen.findByRole('button', { name: 'Aprobar las 3' }))
    await waitFor(() => expect(log.approved).toEqual([['rec-dbl-26', 'rec-ste-26', 'rec-dbl-28']]))
  })

  it('says when there is nothing to decide', async () => {
    mockWidgetApi({ summary: makeSummary({ pending: 0, up: 0, down: 0 }), upcoming: [] })
    renderWithProviders(<RecommendationsWidget />)
    expect(await screen.findByText(/No hay precios por decidir/)).toBeInTheDocument()
  })

  it('only links to the recommendations for a read-only user', async () => {
    mockMe(makeMe({ memberships: [auroraMembership(['revenue.view', 'frontdesk.view'], 'front_desk')] }))
    mockWidgetApi()
    const { queryClient } = renderWithProviders(<RecommendationsWidget />)

    await waitFor(() => expect(queryClient.getQueryData(['me'])).toBeTruthy())
    const widget = await screen.findByRole('region', { name: 'Recomendaciones de precio' })
    expect(await within(widget).findByText('+12 %')).toBeInTheDocument()
    expect(within(widget).queryByRole('button', { name: /Aprobar/ })).not.toBeInTheDocument()
    expect(within(widget).getByRole('link', { name: 'Ver todas' })).toHaveAttribute('href', '/app/revenue')
  })
})
