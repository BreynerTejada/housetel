import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import { useSession } from '@/lib/session'
import { auroraProperty, mockMe } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import type { CalStay } from '../api'
import CalendarPage from '../pages/CalendarPage'
import { IDS } from './fixtures'
import { calendarMe, makeDetail, mockCalendarApi, mockPost, type CalendarApi } from './mocks'

function renderPage() {
  return renderWithProviders(<CalendarPage />, { route: '/app/calendar', path: '/app/calendar' })
}

async function row(name: string) {
  return within(await screen.findByRole('row', { name }))
}

/** Answers a stay action as the server would after applying `change` to the stay. */
function applyOnServer(api: CalendarApi, stayId: string, change: Partial<CalStay>) {
  api.data = { ...api.data, stays: api.data.stays.map((stay) => (stay.id === stayId ? { ...stay, ...change } : stay)) }
  return { status: 200, json: makeDetail(api.data.stays.find((stay) => stay.id === stayId)!, api.data) }
}

/** Picks a bar up with M, presses `keys` and drops it with Enter. */
async function keyboardMove(user: ReturnType<typeof renderPage>['user'], bar: HTMLElement, keys: string) {
  bar.focus()
  await user.keyboard(`m${keys}{Enter}`)
}

beforeEach(() => {
  document.cookie = 'csrftoken=t; path=/'
  useSession.setState({ propertyId: auroraProperty.id, loggedOut: false })
  localStorage.clear()
  mockMe(calendarMe())
})

describe('moving bookings with the keyboard', () => {
  it('moves a booking to a free room of its category right away and offers to undo it', async () => {
    const api = mockCalendarApi()
    mockPost(api, '/bookings/stays/:id/assign/', () => applyOnServer(api, 'luis', { room_id: IDS.r101 }))
    mockPost(api, '/bookings/stays/:id/unassign/', () => applyOnServer(api, 'luis', { room_id: null }))
    const { user } = renderPage()

    await keyboardMove(user, (await row('Sin asignar · Estándar (2)')).getByRole('button', { name: /^Luis Díaz/ }), '{ArrowDown}')

    expect(await screen.findByText('Luis Díaz ahora está en Hab. 101')).toBeInTheDocument()
    expect(api.posts).toEqual([{ path: '/api/v1/bookings/stays/luis/assign/', body: { room_id: IDS.r101, bed_id: null } }])
    expect((await row('Habitación 101')).getByRole('button', { name: /^Luis Díaz/ })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Deshacer' }))
    expect(await screen.findByText('Cambio deshecho')).toBeInTheDocument()
    expect(api.posts.at(-1)).toEqual({ path: '/api/v1/bookings/stays/luis/unassign/', body: null })
    // Back in the second unassigned lane (Luis overlaps Ana).
    expect(await (await row('Sin asignar · Estándar (2)')).findByRole('button', { name: /^Luis Díaz/ })).toBeInTheDocument()
  })

  it('shows the move at once and puts the booking back when the server says no', async () => {
    mockCalendarApi()
    let answer!: () => void
    server.use(
      http.post('/api/v1/bookings/stays/:id/assign/', async () => {
        await new Promise<void>((resolve) => (answer = resolve))
        return HttpResponse.json({ detail: 'La habitación ya está ocupada en esas fechas', code: 'no_availability' }, { status: 409 })
      }),
    )
    const { user } = renderPage()

    await keyboardMove(user, (await row('Sin asignar · Estándar (2)')).getByRole('button', { name: /^Luis Díaz/ }), '{ArrowDown}')
    // Optimistic: already in room 101 while the server thinks.
    expect(await (await row('Habitación 101')).findByRole('button', { name: /^Luis Díaz/ })).toBeInTheDocument()

    answer()
    expect(await screen.findByText('No se pudo hacer el cambio: La habitación ya está ocupada en esas fechas')).toBeInTheDocument()
    await waitFor(() => expect((screen.getByRole('row', { name: 'Habitación 101' }) as HTMLElement).textContent).not.toContain('Luis'))
    expect(within(screen.getByRole('row', { name: 'Sin asignar · Estándar (2)' })).getByRole('button', { name: /^Luis Díaz/ })).toBeInTheDocument()
  })

  it('refuses a room taken on those nights, naming who is there, without calling the server', async () => {
    const api = mockCalendarApi()
    const { user } = renderPage()

    const laura = (await row('Habitación 101')).getByRole('button', { name: /^Laura Gómez/ })
    laura.focus()
    await user.keyboard('m{ArrowDown}')
    expect(await screen.findByText(/Hab\. 102, 13–15 oct 2026\. Ocupada por Mateo Ruiz \(HT-MATEO2\) en esas noches\./)).toBeInTheDocument()
    await user.keyboard('{Enter}')

    expect(await screen.findByText('Ocupada por Mateo Ruiz (HT-MATEO2) en esas noches.', { selector: '[data-sonner-toast] *' })).toBeInTheDocument()
    expect(api.posts).toEqual([])
  })

  it('cancels with Escape', async () => {
    const api = mockCalendarApi()
    const { user } = renderPage()

    const luis = (await row('Sin asignar · Estándar (2)')).getByRole('button', { name: /^Luis Díaz/ })
    luis.focus()
    await user.keyboard('m')
    expect(await screen.findByText('Moviendo la reserva de Luis Díaz.')).toBeInTheDocument()
    await user.keyboard('{ArrowDown}{Escape}')
    expect(await screen.findByText('Movimiento cancelado.')).toBeInTheDocument()
    expect(api.posts).toEqual([])
    expect(luis).toHaveFocus()
  })

  it('asks before changing dates, shows the new total and keeps the agreed prices of the nights that stay', async () => {
    const api = mockCalendarApi()
    mockPost(api, '/bookings/stays/:id/modify-preview/', () => ({
      status: 200,
      json: {
        stay: { id: 'laura', checkin_date: '2026-10-14', checkout_date: '2026-10-16', nights: 2, room_type_id: IDS.dbl, rate_plan_id: 'plan-flex', room_id: IDS.r101, bed_id: null, total_amount: '818400.00' },
        room_kept: true,
        current_total: '761600.00',
        difference: '56800.00',
        reservation_total: '818400.00',
        balance: '437600.00',
      },
    }))
    mockPost(api, '/bookings/stays/:id/modify/', () => applyOnServer(api, 'laura', { checkin: '2026-10-14', checkout: '2026-10-16' }))
    const { user } = renderPage()

    await keyboardMove(user, (await row('Habitación 101')).getByRole('button', { name: /^Laura Gómez/ }), '{ArrowRight}')

    const dialog = within(await screen.findByRole('dialog', { name: '¿Cambiar las fechas?' }))
    expect(dialog.getByText('13–15 oct 2026')).toBeInTheDocument()
    expect(dialog.getByText('14–16 oct 2026')).toBeInTheDocument()
    expect(await dialog.findByText('$ 818.400')).toBeInTheDocument()
    expect(dialog.getByText('+$ 56.800')).toBeInTheDocument()
    await user.click(dialog.getByRole('button', { name: 'Cambiar fechas' }))

    expect(await screen.findByText('Nuevas fechas de Laura Gómez: 14–16 oct 2026')).toBeInTheDocument()
    const body = { checkin: '2026-10-14', checkout: '2026-10-16', reprice: false }
    expect(api.posts).toEqual([
      { path: '/api/v1/bookings/stays/laura/modify-preview/', body },
      { path: '/api/v1/bookings/stays/laura/modify/', body },
    ])
    expect(screen.queryByRole('button', { name: 'Deshacer' })).not.toBeInTheDocument()
  })

  it('a room of another category: an upgrade at the same price, or repricing in the new category', async () => {
    const api = mockCalendarApi()
    mockPost(api, '/bookings/stays/:id/modify-preview/', () => ({
      status: 200,
      json: {
        stay: { id: 'ana', checkin_date: '2026-10-14', checkout_date: '2026-10-16', nights: 2, room_type_id: IDS.ste, rate_plan_id: 'plan-flex', room_id: null, bed_id: null, total_amount: '1547000.00' },
        room_kept: null,
        current_total: '761600.00',
        difference: '785400.00',
        reservation_total: '1547000.00',
        balance: '1547000.00',
      },
    }))
    mockPost(api, '/bookings/stays/:id/assign/', () => applyOnServer(api, 'ana', { room_id: IDS.r301 }))
    const { user } = renderPage()

    // Ana (unassigned DBL) → room 301 (STE): five rows down.
    await keyboardMove(user, (await row('Sin asignar · Estándar')).getByRole('button', { name: /^Ana Pérez/ }), '{ArrowDown>5}')

    const dialog = within(await screen.findByRole('dialog', { name: 'La 301 es de otra categoría' }))
    expect(dialog.getByRole('radio', { name: /Upgrade sin cambiar el precio/ })).toBeChecked()
    expect(await dialog.findByText('Nuevo total: $ 1.547.000 (+$ 785.400).')).toBeInTheDocument()
    await user.click(dialog.getByRole('button', { name: 'Mover' }))

    expect(await screen.findByText('Ana Pérez ahora está en Hab. 301')).toBeInTheDocument()
    expect(api.posts.at(-1)).toEqual({ path: '/api/v1/bookings/stays/ana/assign/', body: { room_id: IDS.r301, bed_id: null, force: true } })
  })

  it('repricing in the new category changes the category first, then takes the room', async () => {
    const api = mockCalendarApi()
    mockPost(api, '/bookings/stays/:id/modify-preview/', () => ({
      status: 200,
      json: {
        stay: { id: 'ana', checkin_date: '2026-10-14', checkout_date: '2026-10-16', nights: 2, room_type_id: IDS.ste, rate_plan_id: 'plan-flex', room_id: null, bed_id: null, total_amount: '1547000.00' },
        room_kept: null,
        current_total: '761600.00',
        difference: '785400.00',
        reservation_total: '1547000.00',
        balance: '1547000.00',
      },
    }))
    mockPost(api, '/bookings/stays/:id/modify/', () => applyOnServer(api, 'ana', { room_type_id: IDS.ste }))
    mockPost(api, '/bookings/stays/:id/assign/', () => applyOnServer(api, 'ana', { room_id: IDS.r301 }))
    const { user } = renderPage()

    await keyboardMove(user, (await row('Sin asignar · Estándar')).getByRole('button', { name: /^Ana Pérez/ }), '{ArrowDown>5}')
    const dialog = within(await screen.findByRole('dialog', { name: 'La 301 es de otra categoría' }))
    await user.click(dialog.getByRole('radio', { name: /Cambiar a Suite Vista al Mar y recotizar/ }))
    await user.click(dialog.getByRole('button', { name: 'Mover' }))

    expect(await screen.findByText('Ana Pérez pasó a Suite Vista al Mar')).toBeInTheDocument()
    expect(api.posts.slice(1)).toEqual([
      { path: '/api/v1/bookings/stays/ana/modify/', body: { room_type_id: IDS.ste, reprice: true } },
      { path: '/api/v1/bookings/stays/ana/assign/', body: { room_id: IDS.r301, bed_id: null } },
    ])
  })
})

describe('moving bookings with the pointer', () => {
  it('drags a bar down to a free room', async () => {
    const api = mockCalendarApi()
    mockPost(api, '/bookings/stays/:id/assign/', () => applyOnServer(api, 'luis', { room_id: IDS.r101 }))
    renderPage()

    const luis = (await row('Sin asignar · Estándar (2)')).getByRole('button', { name: /^Luis Díaz/ })
    // From the middle of lane 2 of "unassigned" (32 px high) to the middle of room 101 (40 px): 16 + 20 px.
    fireEvent.mouseDown(luis, { button: 0, clientX: 100, clientY: 100 })
    fireEvent.mouseMove(document, { clientX: 100, clientY: 110 })
    fireEvent.mouseMove(document, { clientX: 100, clientY: 136 })
    fireEvent.mouseUp(document, { clientX: 100, clientY: 136 })

    expect(await screen.findByText('Luis Díaz ahora está en Hab. 101')).toBeInTheDocument()
    expect(api.posts).toEqual([{ path: '/api/v1/bookings/stays/luis/assign/', body: { room_id: IDS.r101, bed_id: null } }])
  })

  it('stretches the right edge to change the departure (one day = one column)', async () => {
    const api = mockCalendarApi()
    mockPost(api, '/bookings/stays/:id/modify-preview/', () => ({
      status: 200,
      json: {
        stay: { id: 'laura', checkin_date: '2026-10-13', checkout_date: '2026-10-16', nights: 3, room_type_id: IDS.dbl, rate_plan_id: 'plan-flex', room_id: IDS.r101, bed_id: null, total_amount: '1142400.00' },
        room_kept: true,
        current_total: '761600.00',
        difference: '380800.00',
        reservation_total: '1142400.00',
        balance: '761600.00',
      },
    }))
    mockPost(api, '/bookings/stays/:id/modify/', () => applyOnServer(api, 'laura', { checkout: '2026-10-16' }))
    const { user } = renderPage()

    const laura = (await row('Habitación 101')).getByRole('button', { name: /^Laura Gómez/ })
    const handle = laura.parentElement!.querySelector('.cursor-ew-resize')!
    // Days are 60 px wide in jsdom (the minimum for two weeks).
    fireEvent.mouseDown(handle, { button: 0, clientX: 200, clientY: 50 })
    fireEvent.mouseMove(document, { clientX: 230, clientY: 50 })
    fireEvent.mouseMove(document, { clientX: 262, clientY: 50 })
    fireEvent.mouseUp(document, { clientX: 262, clientY: 50 })

    const dialog = within(await screen.findByRole('dialog', { name: '¿Cambiar las fechas?' }))
    expect(dialog.getByText('13–16 oct 2026')).toBeInTheDocument()
    expect(await dialog.findByText('$ 1.142.400')).toBeInTheDocument()
    await user.click(dialog.getByRole('button', { name: 'Cambiar fechas' }))
    expect(await screen.findByText('Nuevas fechas de Laura Gómez: 13–16 oct 2026')).toBeInTheDocument()
    expect(api.posts.at(-1)).toEqual({ path: '/api/v1/bookings/stays/laura/modify/', body: { checkout: '2026-10-16', reprice: false } })
  })
})

describe('from the side panel', () => {
  it('takes the room away with "Quitar habitación"', async () => {
    const api = mockCalendarApi()
    mockPost(api, '/bookings/stays/:id/unassign/', () => applyOnServer(api, 'laura', { room_id: null }))
    const { user } = renderPage()

    await user.click(await screen.findByRole('button', { name: /^Laura Gómez/ }))
    await user.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Quitar habitación' }))

    expect(await screen.findByText('Laura Gómez quedó sin habitación')).toBeInTheDocument()
    expect(api.posts).toEqual([{ path: '/api/v1/bookings/stays/laura/unassign/', body: null }])
  })
})
