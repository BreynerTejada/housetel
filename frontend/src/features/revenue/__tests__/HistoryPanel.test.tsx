import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import { useSession } from '@/lib/session'
import { auroraProperty, makeMe, mockMe } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import type { RevenueRun } from '../api'
import { HistoryPanel } from '../components/HistoryPanel'
import { makeRun } from './fixtures'

const MANUAL = makeRun({
  id: 'run-2',
  started_at: '2026-09-25T09:12:00-05:00',
  trigger: 'manual',
  triggered_by: { id: 'user-1', full_name: 'Valentina Ríos', email: 'owner@casaaurora.co' },
  recommendations_count: 12,
  auto_applied_count: 0,
  expired_count: 2,
  details: {
    count: 12,
    top: [
      { date: '2026-10-10', room_type: 'DBL', change_percent: '20.00', current_price: '320000.00', recommended_price: '384000.00', reasons: ['Ocupación', 'Festivos y puentes'] },
    ],
  },
})
const SCHEDULED = makeRun({ id: 'run-1', ai_provider: '', recommendations_count: 1, auto_applied_count: 1 })

function mockRuns(pages: Record<string, { count: number; results: RevenueRun[] }>) {
  const requested: string[] = []
  server.use(
    http.get('/api/v1/revenue/runs/', ({ request }) => {
      const page = new URL(request.url).searchParams.get('page') ?? '1'
      requested.push(page)
      const body = pages[page] ?? { count: 0, results: [] }
      return HttpResponse.json({ ...body, next: null, previous: null })
    }),
  )
  return requested
}

beforeEach(() => {
  useSession.setState({ propertyId: auroraProperty.id, loggedOut: false })
  mockMe(makeMe())
})

describe('run history', () => {
  it('lists the runs with who ran them, their figures and their summary', async () => {
    mockRuns({ '1': { count: 2, results: [MANUAL, SCHEDULED] } })
    renderWithProviders(<HistoryPanel />)

    const list = await screen.findByRole('list', { name: 'Corridas de revenue' })
    const [manual, scheduled] = Array.from(list.children) as HTMLElement[]
    expect(within(manual).getByText('Manual por Valentina Ríos')).toBeInTheDocument()
    expect(within(manual).getByText('12 recomendaciones')).toBeInTheDocument()
    expect(within(manual).getByText('2 vencidas')).toBeInTheDocument()
    expect(within(manual).getByText('Resumen IA · gemini')).toBeInTheDocument()
    expect(within(manual).getByText(/Suben los sábados con alta ocupación/)).toBeInTheDocument()
    expect(within(manual).getByText(/Ocupación, Festivos y puentes/)).toBeInTheDocument()
    expect(within(scheduled).getByText('Programada')).toBeInTheDocument()
    expect(within(scheduled).getByText('1 aplicada automáticamente')).toBeInTheDocument()
    expect(within(scheduled).getByText('Resumen automático')).toBeInTheDocument()
    expect(within(scheduled).getByText(/Se revisaron las noches/)).toBeInTheDocument()
  })

  it('pages through older runs', async () => {
    const requested = mockRuns({
      '1': { count: 30, results: [MANUAL] },
      '2': { count: 30, results: [SCHEDULED] },
    })
    const { user } = renderWithProviders(<HistoryPanel />)

    expect(await screen.findByText('Página 1 de 2')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Siguientes' }))
    expect(await screen.findByText('Página 2 de 2')).toBeInTheDocument()
    await waitFor(() => expect(requested).toContain('2'))
  })

  it('says when there are no runs yet', async () => {
    mockRuns({})
    renderWithProviders(<HistoryPanel />)
    expect(await screen.findByText('Todavía no hay corridas.')).toBeInTheDocument()
  })
})
