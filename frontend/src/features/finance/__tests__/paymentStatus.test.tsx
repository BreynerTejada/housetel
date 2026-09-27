import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { useLocation } from 'react-router'
import { describe, expect, it } from 'vitest'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import { paymentReturnParams, usePaymentStatus } from '../api'

const REF = 'HT-7K2M9Q-4F7H2K'
const STATUS_URL = `/api/v1/public/finance/intents/${REF}/status/`

function linkStatus(overrides: Record<string, unknown> = {}) {
  return {
    reference: REF,
    status: 'created',
    paid: false,
    amount: '350000.00',
    currency: 'COP',
    method: '',
    reservation_code: 'HT-7K2M9Q',
    property_slug: 'casa-aurora',
    ...overrides,
  }
}

/** What C4's confirmation page or C5's portal (`?paid=1`) do when the gateway sends the guest back. */
function ReturnPage() {
  const { search } = useLocation()
  const { reference, transactionId } = paymentReturnParams(search)
  const payment = usePaymentStatus(reference, { transactionId, intervalMs: 20 })
  return <p>{payment.data ? `${payment.data.status}:${String(payment.data.paid)}` : 'waiting'}</p>
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

describe('usePaymentStatus', () => {
  it('reads what the gateway sends back and polls until the payment is decided', async () => {
    const ids: string[] = []
    server.use(
      http.get(STATUS_URL, ({ request }) => {
        ids.push(new URL(request.url).searchParams.get('id') ?? '')
        return HttpResponse.json(
          ids.length < 3 ? linkStatus({ status: 'pending' }) : linkStatus({ status: 'approved', paid: true, method: 'wompi_card' }),
        )
      }),
    )
    renderWithProviders(<ReturnPage />, { route: `/booking/HT-7K2M9Q/confirmed?payment_ref=${REF}&id=1234-1610641025-49201` })

    expect(await screen.findByText('approved:true')).toBeInTheDocument()
    expect(ids).toEqual(['1234-1610641025-49201', '1234-1610641025-49201', '1234-1610641025-49201'])
    await sleep(120)
    expect(ids).toHaveLength(3) // no more requests once it is paid
  })

  it('stops asking when the payment is declined', async () => {
    let calls = 0
    server.use(
      http.get(STATUS_URL, () => {
        calls += 1
        return HttpResponse.json(linkStatus({ status: 'declined' }))
      }),
    )
    renderWithProviders(<ReturnPage />, { route: `/g/token?paid=1&payment_ref=${REF}` })

    expect(await screen.findByText('declined:false')).toBeInTheDocument()
    await sleep(120)
    expect(calls).toBe(1)
  })

  it('gives up on a reference the server does not know', async () => {
    let calls = 0
    server.use(
      http.get(STATUS_URL, () => {
        calls += 1
        return HttpResponse.json({ detail: 'No encontrado.', code: 'not_found' }, { status: 404 })
      }),
    )
    renderWithProviders(<ReturnPage />, { route: `/g/token?paid=1&payment_ref=${REF}` })
    await sleep(150)
    expect(calls).toBe(1)
  })

  it('does not ask anything when the page was opened without a payment reference', async () => {
    renderWithProviders(<ReturnPage />, { route: '/g/token' })
    await sleep(60)
    expect(screen.getByText('waiting')).toBeInTheDocument() // MSW fails the test on any unhandled request
  })
})

describe('paymentReturnParams', () => {
  it('takes the reference Housetel adds and the transaction id Wompi adds', () => {
    expect(paymentReturnParams(`?paid=1&payment_ref=${REF}&id=1234-1-1`)).toEqual({ reference: REF, transactionId: '1234-1-1' })
    expect(paymentReturnParams(new URLSearchParams('paid=1'))).toEqual({ reference: null, transactionId: null })
  })
})
