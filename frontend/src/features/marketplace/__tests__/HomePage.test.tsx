import { screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { renderWithProviders } from '@/test/render'
import HomePage from '../pages/HomePage'
import { serveHome } from './fixtures'

function renderHome() {
  return renderWithProviders(<HomePage />, { route: '/', path: '/', routes: [{ path: '/search', element: <p>resultados</p> }] })
}

describe('HomePage', () => {
  it('opens with the direct-booking promise and the search box', async () => {
    serveHome()
    renderHome()

    expect(screen.getByRole('heading', { level: 1, name: 'Reserva directo con el hotel.' })).toBeInTheDocument()
    expect(screen.getByRole('search', { name: 'Buscar alojamiento' })).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: 'Hotel Casa Aurora' })).toBeInTheDocument()
  })

  it('stands every destination at its altitude and links it to its hotels', async () => {
    serveHome()
    renderHome()

    const profile = await screen.findByRole('list', { name: 'Destinos con alojamientos en Housetel, ordenados por altitud' })
    const links = within(profile).getAllByRole('link')
    // from the sea up
    expect(links.map((link) => link.getAttribute('aria-label'))).toEqual([
      'Cartagena: 2 m sobre el nivel del mar, clima cálido. 2 alojamientos',
      'Medellín: 1.495 m sobre el nivel del mar, clima templado. 1 alojamiento',
      'Bogotá: 2.640 m sobre el nivel del mar, clima frío. 1 alojamiento',
    ])
    expect(links[2]).toHaveAttribute('href', '/search?city=Bogot%C3%A1&adults=2')
  })

  it('searches a destination picked from the suggestions with the chosen party', async () => {
    serveHome()
    const { user, router } = renderHome()

    const destination = screen.getByRole('combobox', { name: 'Destino' })
    await user.type(destination, 'mede')
    await user.click(await screen.findByRole('option', { name: /Medellín/ }))
    expect(destination).toHaveValue('Medellín')

    await user.click(screen.getByRole('button', { name: /2 adultos/ }))
    await user.click(screen.getByRole('button', { name: 'Agregar un niño' }))
    await user.click(screen.getByRole('button', { name: 'Listo' }))
    await user.click(screen.getByRole('button', { name: 'Buscar' }))

    expect(router.state.location.pathname).toBe('/search')
    const params = new URLSearchParams(router.state.location.search)
    expect(Object.fromEntries(params)).toEqual({ city: 'Medellín', adults: '2', children: '1' })
  })

  it('navigates the suggestions with the keyboard', async () => {
    serveHome()
    const { user } = renderHome()

    const destination = screen.getByRole('combobox', { name: 'Destino' })
    await user.click(destination)
    await screen.findByRole('option', { name: /Cartagena/ })
    await user.keyboard('{ArrowDown}{ArrowDown}{Enter}')

    expect(destination).toHaveValue('Cartagena')
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
  })
})
