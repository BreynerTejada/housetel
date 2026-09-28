import { screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import { useSession } from '@/lib/session'
import { auroraProperty, mockMe } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import CalendarPage from '../pages/CalendarPage'
import { IDS, makeCalendar, makeStay } from './fixtures'
import { calendarMe, mockCalendarApi } from './mocks'

function renderPage(route = '/app/calendar') {
  return renderWithProviders(<CalendarPage />, { route, path: '/app/calendar' })
}

async function row(name: string) {
  return within(await screen.findByRole('row', { name }))
}

beforeEach(() => {
  document.cookie = 'csrftoken=t; path=/'
  useSession.setState({ propertyId: auroraProperty.id, loggedOut: false })
  localStorage.clear()
  mockMe(calendarMe())
})

describe('calendar grid', () => {
  it('asks for two weeks from the day before the business date, plus the day before for departures', async () => {
    const api = mockCalendarApi()
    renderPage()

    expect(await screen.findByRole('heading', { name: 'Calendario', level: 1 })).toBeInTheDocument()
    await screen.findByRole('table', { name: /Calendario de reservas/ })
    expect(api.calendarRequests[0].searchParams.get('start')).toBe('2026-10-11')
    expect(api.calendarRequests[0].searchParams.get('end')).toBe('2026-10-26')
    // Prices for the nights on screen, in the language on screen.
    await waitFor(() => expect(api.gridRequests).toHaveLength(1))
    expect(Object.fromEntries(api.gridRequests[0].searchParams)).toEqual({ start: '2026-10-12', end: '2026-10-26', lang: 'es' })
  })

  it('lists categories, their unassigned lanes, rooms, dorm rooms and beds', async () => {
    mockCalendarApi()
    renderPage()

    const table = await screen.findByRole('table', { name: /Calendario de reservas/ })
    await within(table).findByRole('row', { name: 'Habitación 101' })
    const names = within(table)
      .getAllByRole('row')
      .map((element) => element.getAttribute('aria-label'))
      .filter(Boolean)
    expect(names).toEqual([
      'Estándar (DBL)',
      'Sin asignar · Estándar',
      'Sin asignar · Estándar (2)',
      'Habitación 101',
      'Habitación 102',
      'Suite Vista al Mar (STE)',
      'Sin asignar · Suite Vista al Mar',
      'Habitación 301',
      'Dormitorio 6 camas (D6)',
      'Sin asignar · Dormitorio 6 camas',
      'Dormitorio D1',
      'Cama A · D1',
      'Cama B · D1',
    ])
  })

  it('draws each stay in its row with guest, code, status, dates, room and flags', async () => {
    mockCalendarApi()
    renderPage()

    expect(
      (await row('Habitación 101')).getByRole('button', {
        name: /^Laura Gómez · HT-LAURA1 · Confirmada · 13–15 oct 2026 · 2 noches · Hab\. 101 · Saldo pendiente · Teléfono$/,
      }),
    ).toBeInTheDocument()
    expect((await row('Habitación 102')).getByRole('button', { name: /^Mateo Ruiz · HT-MATEO2 · En casa · .* · BookSim$/ })).toBeInTheDocument()
    expect(
      (await row('Sin asignar · Estándar')).getByRole('button', {
        name: /^Ana Pérez · HT-ANA003 · Tentativa · 14–16 oct 2026 · 2 noches · Sin asignar/,
      }),
    ).toBeInTheDocument()
    expect((await row('Sin asignar · Estándar (2)')).getByRole('button', { name: /^Luis Díaz/ })).toBeInTheDocument()
    expect(
      (await row('Habitación 301')).getByRole('button', { name: /^Sofía Mejía · .* · VIP · Upgrade: reservó Estándar/ }),
    ).toBeInTheDocument()
    expect((await row('Cama A · D1')).getByRole('button', { name: /^Beatriz Soto · .* · Cama A · D1/ })).toBeInTheDocument()
  })

  it('shows blocks hatched in their room, and whole-room dorm blocks on every bed', async () => {
    mockCalendarApi()
    renderPage()

    expect(
      (await row('Habitación 102')).getByRole('img', { name: 'Bloqueada · Mantenimiento · Pintura · 16–18 oct 2026' }),
    ).toBeInTheDocument()
    expect((await row('Dormitorio D1')).getByRole('img', { name: /Fuera de servicio · Fumigación/ })).toBeInTheDocument()
    expect((await row('Cama B · D1')).getAllByRole('img', { name: /^Bloqueada/ })).toHaveLength(2)
  })

  it('shows free units and the nightly price of each category, and marks holidays and today', async () => {
    mockCalendarApi()
    renderPage()

    const dbl = await row('Estándar (DBL)')
    // DBL availability: 12 → 1, 13 → 0, 14 → −1, 15 → 0, 16 → 0, 17 → 1, 18 → 2 (nothing known after the 18th).
    expect(dbl.getByText('Sobrevendida: 1')).toBeInTheDocument()
    expect(dbl.getAllByText('Lleno')).toHaveLength(3)
    expect(dbl.getAllByText('1 libre')).toHaveLength(2)
    expect(dbl.getAllByText('2 libres')).toHaveLength(1)
    // Weeknights at the base price, Friday and Saturday nights 15 % more (the rate grid mock).
    expect(await dbl.findAllByText(/^Tarifa flexible: \$\s320\.000$/)).toHaveLength(10)
    expect(dbl.getAllByText(/^Tarifa flexible: \$\s368\.000$/)).toHaveLength(4)
    expect((await row('Suite Vista al Mar (STE)')).getByText(/Cerrada a la venta/)).toBeInTheDocument()

    expect(screen.getByRole('columnheader', { name: 'lun 12 oct · Día de la Raza' })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'mar 13 oct · Hoy' })).toBeInTheDocument()
  })

  it('shows how many beds of each dorm room are free every night', async () => {
    mockCalendarApi()
    renderPage()

    const dorm = await row('Dormitorio D1')
    expect(dorm.getAllByText('1 de 2 camas libres').length).toBeGreaterThan(0)
    expect(dorm.getByText('0 de 2 camas libres')).toBeInTheDocument() // the 16th, whole room blocked
  })

  it('starts busy unassigned groups folded, but what the user unfolded stays unfolded', async () => {
    const data = makeCalendar()
    for (let i = 0; i < 5; i += 1) {
      data.stays.push(makeStay({ id: `walk${i}`, guest_name: `Mochilero ${i}`, room_type_id: IDS.dorm, checkin: '2026-10-14', checkout: '2026-10-15', adults: 1 }))
    }
    mockCalendarApi(data)
    const { user } = renderPage()

    const folded = await row('Sin asignar · Dormitorio 6 camas')
    expect(folded.queryByRole('button', { name: /^Mochilero 0/ })).not.toBeInTheDocument()
    expect(folded.getByText('5 sin asignar')).toBeInTheDocument() // the 14th: five walk-ins

    await user.click(screen.getByRole('button', { name: 'Expandir sin asignar de Dormitorio 6 camas' }))
    expect(await screen.findByRole('button', { name: /^Mochilero 4/ })).toBeInTheDocument()
    expect(JSON.parse(localStorage.getItem('housetel.calendar.collapsed') ?? '{}')).toEqual({ 'un:rt-d6': false })
  })

  it('folds a category and its unassigned group, and remembers it', async () => {
    mockCalendarApi()
    const { user } = renderPage()

    await user.click(await screen.findByRole('button', { name: 'Contraer Estándar' }))
    expect(screen.queryByRole('row', { name: 'Habitación 101' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Expandir Estándar' })).toHaveAttribute('aria-expanded', 'false')

    await user.click(screen.getByRole('button', { name: 'Contraer sin asignar de Dormitorio 6 camas' }))
    const folded = await row('Sin asignar · Dormitorio 6 camas')
    expect(folded.queryByRole('button', { name: /Carl Jensen/ })).not.toBeInTheDocument()
    expect(folded.getByText('1 sin asignar')).toBeInTheDocument() // Carl, the 13th

    // What the user folds is remembered as an override, so the defaults keep applying to the other groups.
    expect(JSON.parse(localStorage.getItem('housetel.calendar.collapsed') ?? '{}')).toEqual({ 'rt:rt-dbl': true, 'un:rt-d6': true })
  })
})

describe('calendar toolbar', () => {
  it('moves a week at a time, jumps back to today and asks for each range', async () => {
    const api = mockCalendarApi()
    const { user } = renderPage()
    await screen.findByRole('table', { name: /Calendario de reservas/ })

    await user.click(screen.getByRole('button', { name: 'Semana siguiente' }))
    await waitFor(() => expect(api.calendarRequests.at(-1)?.searchParams.get('start')).toBe('2026-10-18'))
    expect(api.calendarRequests.at(-1)?.searchParams.get('end')).toBe('2026-11-02')
    expect(await screen.findByRole('table', { name: 'Calendario de reservas del 19 oct – 1 nov 2026' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Semana anterior' }))
    await user.click(screen.getByRole('button', { name: 'Semana anterior' }))
    expect(await screen.findByRole('table', { name: 'Calendario de reservas del 5–18 oct 2026' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Hoy' }))
    expect(await screen.findByRole('table', { name: 'Calendario de reservas del 12–25 oct 2026' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Hoy' })).toBeDisabled()
  })

  it('shows 7, 14 or 30 days and remembers the choice', async () => {
    const api = mockCalendarApi()
    const { user } = renderPage()
    await screen.findByRole('table', { name: /Calendario de reservas/ })

    await user.click(screen.getByRole('radio', { name: '30 días' }))
    await waitFor(() => expect(api.calendarRequests.at(-1)?.searchParams.get('end')).toBe('2026-11-11'))
    // The header row: the room column plus one column per day.
    expect(await screen.findAllByRole('columnheader')).toHaveLength(31)
    expect(localStorage.getItem('housetel.calendar.span')).toBe('30')
  })

  it('shows only the chosen categories and statuses', async () => {
    mockCalendarApi()
    const { user } = renderPage()
    await screen.findByRole('row', { name: 'Habitación 101' })

    await user.click(screen.getByRole('button', { name: /Categorías: Todas/ }))
    await user.click(await screen.findByRole('menuitemcheckbox', { name: /Estándar/ }))
    await user.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('row', { name: 'Habitación 101' })).not.toBeInTheDocument())
    expect(screen.getByRole('row', { name: 'Habitación 301' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Categorías: 2 de 3/ })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Estados: Todos/ }))
    await user.click(await screen.findByRole('menuitemcheckbox', { name: /Tentativa/ }))
    await user.click(screen.getByRole('menuitemcheckbox', { name: /Confirmada/ }))
    await user.keyboard('{Escape}')
    // Sofía is confirmed (hidden); blocks always show.
    await waitFor(() => expect(screen.queryByRole('button', { name: /^Sofía Mejía/ })).not.toBeInTheDocument())
    expect((await row('Cama B · D1')).getAllByRole('img', { name: /^Bloqueada/ })).toHaveLength(2)
  })

  it('finds a booking by guest or code and takes the focus to it', async () => {
    mockCalendarApi()
    const { user } = renderPage()
    await screen.findByRole('row', { name: 'Habitación 101' })

    await user.type(screen.getByRole('searchbox', { name: 'Buscar una reserva en el calendario' }), 'sofia')
    expect(screen.getByText('1 en estas fechas')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Ir a la siguiente' }))
    await waitFor(() => expect(screen.getByRole('button', { name: /^Sofía Mejía/ })).toHaveFocus())

    // Every code starts with HT-: the eight stays of the range, visited top to bottom, then left to right.
    const search = screen.getByRole('searchbox', { name: 'Buscar una reserva en el calendario' })
    await user.clear(search)
    await user.type(search, 'HT-{Enter}')
    expect(screen.getByText('8 en estas fechas')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByRole('button', { name: /^Ana Pérez/ })).toHaveFocus())
    await user.click(search)
    await user.keyboard('{Enter}')
    await waitFor(() => expect(screen.getByRole('button', { name: /^Luis Díaz/ })).toHaveFocus())
  })

  it('unfolds the group of the next match when it is folded', async () => {
    mockCalendarApi()
    const { user } = renderPage()
    await user.click(await screen.findByRole('button', { name: 'Contraer sin asignar de Dormitorio 6 camas' }))
    expect(screen.queryByRole('button', { name: /^Carl Jensen/ })).not.toBeInTheDocument()

    await user.type(screen.getByRole('searchbox', { name: 'Buscar una reserva en el calendario' }), 'carl{Enter}')
    await waitFor(() => expect(screen.getByRole('button', { name: /^Carl Jensen/ })).toHaveFocus())
  })
})
