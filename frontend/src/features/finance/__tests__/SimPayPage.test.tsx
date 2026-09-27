import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import { leavePage } from '../navigation'
import SimPayPage from '../pages/SimPayPage'
import { makeSimIntent } from './fixtures'
import type { SimIntent } from '../api'

vi.mock('../navigation', () => ({ leavePage: vi.fn() }))

const REF = 'HT-7K2M9Q-4F7H2K'
const URL = `/api/v1/public/finance/sim/intents/${REF}/`

function serve(intent: SimIntent) {
  const decisions: Record<string, unknown>[] = []
  let current = intent
  server.use(
    http.get(URL, () => HttpResponse.json(current)),
    http.post(`${URL}decide/`, async ({ request }) => {
      const body = (await request.json()) as { outcome: string; method: string }
      decisions.push(body)
      current = { ...current, status: body.outcome, method: `wompi_${body.method}` }
      return HttpResponse.json(current)
    }),
  )
  return decisions
}

function renderPage() {
  return renderWithProviders(<SimPayPage />, { route: `/sim/pay/${REF}`, path: '/sim/pay/:reference' })
}

beforeEach(() => {
  document.cookie = 'csrftoken=t; path=/' // decisions are POSTs: the client sends X-CSRFToken from this cookie
})

describe('SimPayPage', () => {
  it('looks like a checkout and says clearly that it is a simulation', async () => {
    serve(makeSimIntent())
    renderPage()

    expect(await screen.findByRole('heading', { name: 'Hotel Casa Aurora' })).toBeInTheDocument()
    expect(screen.getByRole('status', { name: 'Modo simulación' })).toHaveTextContent(/ningún cobro es real/i)
    expect(screen.getByText('$ 350.000')).toBeInTheDocument()
    expect(screen.getByText(REF)).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Tarjeta' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByLabelText('Número de la tarjeta')).toHaveValue('4242 4242 4242 4242')
  })

  it('approves with the chosen method and takes the guest back to the hotel', async () => {
    const decisions = serve(makeSimIntent())
    const { user } = renderPage()

    await user.click(await screen.findByRole('tab', { name: 'Nequi' }))
    await user.click(screen.getByRole('button', { name: 'Pagar $ 350.000' }))

    expect(await screen.findByRole('heading', { name: 'Pago aprobado' })).toBeInTheDocument()
    expect(decisions).toEqual([{ outcome: 'approved', method: 'nequi' }])
    await user.click(screen.getByRole('button', { name: 'Volver a Hotel Casa Aurora' }))
    expect(leavePage).toHaveBeenCalledWith(makeSimIntent().return_url)
  })

  it('declines and lets the guest try again', async () => {
    const decisions = serve(makeSimIntent())
    const { user } = renderPage()

    await user.click(await screen.findByRole('button', { name: 'Simular rechazo' }))

    expect(await screen.findByRole('heading', { name: 'Pago rechazado' })).toBeInTheDocument()
    expect(decisions).toEqual([{ outcome: 'declined', method: 'card' }])
    await user.click(screen.getByRole('button', { name: 'Intentar de nuevo' }))
    expect(await screen.findByRole('button', { name: 'Pagar $ 350.000' })).toBeInTheDocument()
  })

  it('lets the link expire', async () => {
    const decisions = serve(makeSimIntent())
    const { user } = renderPage()

    await user.click(await screen.findByRole('button', { name: 'Dejar vencer el link' }))

    expect(await screen.findByRole('heading', { name: 'El link de pago venció' })).toBeInTheDocument()
    expect(decisions).toEqual([{ outcome: 'expired', method: 'card' }])
    expect(screen.queryByRole('button', { name: /Pagar/ })).not.toBeInTheDocument()
  })

  it('shows a paid link as paid', async () => {
    serve(makeSimIntent({ status: 'approved', method: 'wompi_pse' }))
    renderPage()
    const result = await screen.findByRole('region', { name: 'Pago aprobado' })
    expect(within(result).getByText('PSE')).toBeInTheDocument()
  })

  it('explains unknown links', async () => {
    server.use(http.get(URL, () => HttpResponse.json({ detail: 'No encontrado.', code: 'not_found' }, { status: 404 })))
    renderPage()
    expect(await screen.findByRole('heading', { name: 'No encontramos este pago' })).toBeInTheDocument()
  })

  it('works in English', async () => {
    serve(makeSimIntent())
    const { user } = renderPage()
    await user.click(await screen.findByRole('button', { name: 'English' }))
    await waitFor(() => expect(screen.getByRole('status', { name: 'Simulation mode' })).toBeInTheDocument())
    expect(screen.getByRole('button', { name: 'Pay $ 350.000' })).toBeInTheDocument()
  })
})
