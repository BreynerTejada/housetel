import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import { useSession } from '@/lib/session'
import { mockMe } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import NightAuditPage from '../pages/NightAuditPage'
import { deskMe, FRONT_DESK, makePreview, makeReport, page } from './fixtures'

const PREVIEW = '/api/v1/frontdesk/night-audit/preview/'
const RUN = '/api/v1/frontdesk/night-audit/run/'
const REPORTS = '/api/v1/frontdesk/night-audit/reports/'

function renderAudit() {
  return renderWithProviders(<NightAuditPage />, { route: '/app/night-audit', path: '/app/night-audit' })
}

beforeEach(() => {
  useSession.setState({ propertyId: null, loggedOut: false })
  document.cookie = 'csrftoken=t; path=/'
})

describe('NightAuditPage', () => {
  it('shows what closing the day will do and closes it once confirmed', async () => {
    mockMe(deskMe(['*']))
    let body: unknown
    let meRequests = 0
    server.use(
      http.get(PREVIEW, () => HttpResponse.json(makePreview())),
      http.get(REPORTS, () => HttpResponse.json(page([]))),
      http.post(RUN, async ({ request }) => {
        body = await request.json()
        return HttpResponse.json(makeReport({ id: 'report-new', business_date: '2026-10-01' }), { status: 201 })
      }),
      http.get('/api/v1/accounts/me/', () => {
        meRequests += 1
        return HttpResponse.json(deskMe(['*']))
      }),
    )
    const { user } = renderAudit()

    const preview = await screen.findByRole('region', { name: 'Cierre del día' })
    expect(await within(preview).findByText('jueves 1 de octubre')).toBeInTheDocument()
    expect(within(preview).getByText('18 noches')).toBeInTheDocument()
    expect(within(preview).getByText('$ 6.426.000')).toBeInTheDocument()
    const noShow = within(preview).getByRole('listitem', { name: /HT-NOSHOW/ })
    expect(within(noShow).getByText('Carlos Pérez')).toBeInTheDocument()
    expect(within(noShow).getByText('$ 380.800')).toBeInTheDocument()

    const before = meRequests
    await user.click(within(preview).getByRole('button', { name: 'Cerrar el día' }))
    const dialog = await screen.findByRole('dialog', { name: '¿Cerrar el 1 oct?' })
    await user.click(within(dialog).getByRole('button', { name: 'Cerrar el día' }))

    await waitFor(() => expect(body).toEqual({ business_date: '2026-10-01' }))
    await waitFor(() => expect(meRequests).toBeGreaterThan(before))
  })

  it('explains why a day that has not started cannot be closed', async () => {
    mockMe(deskMe(['*']))
    server.use(
      http.get(PREVIEW, () => HttpResponse.json(makePreview({ can_run: false, reason: 'audit_ahead', due: false, calendar_date: '2026-09-30', summary: null }))),
      http.get(REPORTS, () => HttpResponse.json(page([]))),
    )
    renderAudit()

    const preview = await screen.findByRole('region', { name: 'Cierre del día' })
    expect(await within(preview).findByText(/todavía no ha empezado/)).toBeInTheDocument()
    expect(within(preview).getByRole('button', { name: 'Cerrar el día' })).toBeDisabled()
  })

  it('lists the closing reports with their figures', async () => {
    mockMe(deskMe(['*']))
    server.use(
      http.get(PREVIEW, () => HttpResponse.json(makePreview())),
      http.get(REPORTS, () =>
        HttpResponse.json(page([makeReport(), makeReport({ id: 'report-0', business_date: '2026-09-29', status: 'partial', summary: { ...makeReport().summary, errors: [{ step: 'room_charges', reservation_id: 'r', code: 'HT-ERR001', error_code: 'folio_closed', error: 'El folio está cerrado' }] } })])),
      ),
    )
    const { user } = renderAudit()

    const history = await screen.findByRole('region', { name: 'Cierres anteriores' })
    const report = await within(history).findByRole('listitem', { name: /30 sep/ })
    expect(within(report).getByText('Completada')).toBeInTheDocument()
    expect(within(report).getByText('62,5%')).toBeInTheDocument()
    const partial = within(history).getByRole('listitem', { name: /29 sep/ })
    expect(within(partial).getByText('Con pendientes')).toBeInTheDocument()
    await user.click(within(partial).getByRole('button', { name: 'Ver detalle' }))
    expect(await within(partial).findByText(/El folio está cerrado/)).toBeInTheDocument()
  })

  it('the front desk sees the reports but cannot run the audit', async () => {
    mockMe(deskMe(FRONT_DESK))
    server.use(http.get(REPORTS, () => HttpResponse.json(page([makeReport()]))))
    renderAudit()

    expect(await screen.findByRole('region', { name: 'Cierres anteriores' })).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Cierre del día' })).not.toBeInTheDocument()
    expect(screen.getByText(/Solo quien tiene permiso de auditoría/)).toBeInTheDocument()
  })
})
