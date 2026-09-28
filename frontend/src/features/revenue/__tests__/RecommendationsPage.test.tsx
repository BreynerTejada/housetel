import { screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import { useSession } from '@/lib/session'
import { auroraMembership, auroraProperty, makeMe, mockMe } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import RevenuePage from '../pages/RevenuePage'
import { makeRecommendation, mockRevenueApi } from './fixtures'

function renderPage() {
  return renderWithProviders(<RevenuePage />, { route: '/app/revenue' })
}

const cellOf = (name: RegExp) => screen.findByRole('gridcell', { name })

beforeEach(() => {
  document.cookie = 'csrftoken=t; path=/'
  useSession.setState({ propertyId: auroraProperty.id, loggedOut: false })
  localStorage.clear()
  mockMe(makeMe())
})

describe('recommendations heatmap', () => {
  it('shows each category × night with its recommended change and the figures of what is pending', async () => {
    const log = mockRevenueApi()
    renderPage()

    const grid = await screen.findByRole('grid', { name: 'Recomendaciones de precio por categoría y noche' })
    expect(within(grid).getByRole('rowheader', { name: /Estándar/ })).toBeInTheDocument()
    expect(within(grid).getByRole('rowheader', { name: /Suite Vista al Mar/ })).toBeInTheDocument()
    const saturday = await cellOf(/^Estándar, sáb 26 sep: subir \+12 %/)
    expect(saturday).toHaveTextContent('+12')
    expect(saturday).toHaveAttribute('data-step', '3')
    expect(await cellOf(/^Estándar, lun 28 sep: bajar −8 %/)).toHaveAttribute('data-step', '-2')
    expect(await cellOf(/^Estándar, dom 27 sep: .*aplicada/)).toHaveAttribute('data-status', 'applied')
    // 30 nights from the business date, end exclusive
    expect(log.calendarRequests[0].searchParams.get('start')).toBe('2026-09-25')
    expect(log.calendarRequests[0].searchParams.get('end')).toBe('2026-10-25')
    expect(log.calendarRequests[0].searchParams.get('lang')).toBe('es')

    const pending = screen.getByRole('group', { name: 'Pendientes' })
    expect(pending).toHaveTextContent('3')
    expect(pending).toHaveTextContent('2 suben · 1 baja')
    expect(screen.getByRole('group', { name: 'Impacto estimado' })).toHaveTextContent('$ 1,3 M')
    // the AI summary of the last run, labelled as such
    expect(screen.getByText(/Suben los sábados con alta ocupación/)).toBeInTheDocument()
    expect(screen.getByText('Resumen IA · gemini')).toBeInTheDocument()
  })

  it('approves several nights at once and applies them', async () => {
    const log = mockRevenueApi()
    const { user } = renderPage()

    const dbl = await cellOf(/^Estándar, sáb 26 sep/)
    const suite = await cellOf(/^Suite Vista al Mar, sáb 26 sep/)
    await user.click(dbl)
    await user.click(suite)
    expect(dbl).toHaveAttribute('aria-selected', 'true')
    expect(suite).toHaveAttribute('aria-selected', 'true')

    const bar = screen.getByRole('region', { name: 'Selección' })
    expect(bar).toHaveTextContent('2 seleccionadas')
    await user.click(within(bar).getByRole('button', { name: 'Aprobar y aplicar' }))

    await waitFor(() => expect(log.decisions).toHaveLength(1))
    expect(log.decisions[0]).toEqual({ decision: 'approve', ids: ['rec-dbl-26', 'rec-ste-26'] })
    expect(await screen.findByText('2 recomendaciones aprobadas y aplicadas a la grilla')).toBeInTheDocument()
    // the map comes back with those nights applied and nothing selected
    await waitFor(() => expect(screen.queryByRole('region', { name: 'Selección' })).not.toBeInTheDocument())
    expect(await cellOf(/^Estándar, sáb 26 sep: .*aplicada/)).toHaveAttribute('data-status', 'applied')
  })

  it('selects every pending night of the screen, of one category or of one night', async () => {
    const log = mockRevenueApi()
    const { user } = renderPage()

    await user.click(await screen.findByRole('button', { name: 'Seleccionar las pendientes de Estándar' }))
    expect(screen.getByRole('region', { name: 'Selección' })).toHaveTextContent('2 seleccionadas')
    await user.click(screen.getByRole('button', { name: 'Seleccionar las pendientes del sáb 26 sep' }))
    expect(screen.getByRole('region', { name: 'Selección' })).toHaveTextContent('3 seleccionadas')
    await user.click(screen.getByRole('button', { name: 'Limpiar selección' }))
    expect(screen.queryByRole('region', { name: 'Selección' })).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Seleccionar las 3 pendientes' }))
    await user.click(within(screen.getByRole('region', { name: 'Selección' })).getByRole('button', { name: 'Rechazar' }))
    await waitFor(() => expect(log.decisions).toHaveLength(1))
    expect(log.decisions[0].decision).toBe('reject')
    expect([...log.decisions[0].ids].sort()).toEqual(['rec-dbl-26', 'rec-dbl-28', 'rec-ste-26'])
  })

  it('selects with the keyboard: arrows move, Space toggles', async () => {
    mockRevenueApi()
    const { user } = renderPage()

    const dbl = await cellOf(/^Estándar, sáb 26 sep/)
    await user.click(dbl) // selects it
    await user.keyboard('{ArrowDown}')
    const suite = await cellOf(/^Suite Vista al Mar, sáb 26 sep/)
    expect(suite).toHaveFocus()
    await user.keyboard(' ')
    expect(suite).toHaveAttribute('aria-selected', 'true')
    await user.keyboard('{ArrowUp} ')
    expect(dbl).toHaveAttribute('aria-selected', 'false')
  })

  it('explains the night that was clicked: rules, limits and the explanation', async () => {
    const log = mockRevenueApi()
    const { user } = renderPage()

    await user.click(await cellOf(/^Estándar, sáb 26 sep/))
    const detail = await screen.findByRole('region', { name: 'Detalle de la recomendación' })
    await waitFor(() => expect(log.detailRequests).toContain('rec-dbl-26'))
    expect(await within(detail).findByText('Ocupación')).toBeInTheDocument()
    expect(within(detail).getByText('Ocupación en libros: 88 %')).toBeInTheDocument()
    expect(within(detail).getByText('+15 %')).toBeInTheDocument()
    expect(within(detail).getByText('Sábados')).toBeInTheDocument()
    expect(within(detail).getByText(/Tope de cambio diario de 20 %/)).toBeInTheDocument()
    expect(within(detail).getByText(/ocupación del 88 % \(\+15 %\); sábado \(\+8 %\)/)).toBeInTheDocument()
  })

  it('approves the night on screen from its detail', async () => {
    const log = mockRevenueApi()
    const { user } = renderPage()

    await user.click(await cellOf(/^Estándar, lun 28 sep/))
    const detail = await screen.findByRole('region', { name: 'Detalle de la recomendación' })
    await user.click(await within(detail).findByRole('button', { name: 'Aprobar y aplicar' }))
    await waitFor(() => expect(log.decisions).toEqual([{ decision: 'approve', ids: ['rec-dbl-28'] }]))
  })

  it('reports the nights that could not be written to the grid', async () => {
    mockRevenueApi({
      decisionResult: (_decision, ids) => ({
        updated: 1,
        skipped: [],
        errors: [{ id: ids[0], code: 'no_rate', detail: 'La noche no tiene precio configurado' }],
        recommendations: [makeRecommendation({ status: 'approved', apply_error: 'La noche no tiene precio configurado' })],
      }),
    })
    const { user } = renderPage()

    await user.click(await cellOf(/^Estándar, sáb 26 sep/))
    await user.click(within(screen.getByRole('region', { name: 'Selección' })).getByRole('button', { name: 'Aprobar y aplicar' }))
    expect(await screen.findByText(/1 no se pudo aplicar: La noche no tiene precio configurado/)).toBeInTheDocument()
  })

  it('lets a read-only user explore but not select or decide', async () => {
    mockMe(makeMe({ memberships: [auroraMembership(['revenue.view', 'rates.view'], 'front_desk')] }))
    mockRevenueApi()
    const { user } = renderPage()

    const dbl = await cellOf(/^Estándar, sáb 26 sep/)
    expect(dbl).not.toHaveAttribute('aria-selected')
    await user.click(dbl)
    expect(screen.queryByRole('region', { name: 'Selección' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Seleccionar las/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Correr ahora' })).not.toBeInTheDocument()
    const detail = await screen.findByRole('region', { name: 'Detalle de la recomendación' })
    expect(await within(detail).findByText('Ocupación')).toBeInTheDocument()
    expect(within(detail).queryByRole('button', { name: 'Aprobar y aplicar' })).not.toBeInTheDocument()
  })

  it('offers the same recommendations as a list, with the same selection', async () => {
    const log = mockRevenueApi()
    const { user } = renderPage()

    await user.click(await screen.findByRole('radio', { name: 'Lista' }))
    const table = await screen.findByRole('table', { name: 'Recomendaciones de precio' })
    const rows = within(table).getAllByRole('row').slice(1)
    expect(rows).toHaveLength(5) // 3 pending + 1 applied + 1 rejected
    await user.click(within(table).getByRole('checkbox', { name: 'Seleccionar Estándar, lun 28 sep' }))
    await user.click(within(screen.getByRole('region', { name: 'Selección' })).getByRole('button', { name: 'Aprobar y aplicar' }))
    await waitFor(() => expect(log.decisions).toEqual([{ decision: 'approve', ids: ['rec-dbl-28'] }]))
  })
})
