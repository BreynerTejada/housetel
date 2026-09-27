import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import { useSession } from '@/lib/session'
import { auroraProperty, makeMe, mockMe } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import type { Tax } from '../api'
import TaxesPage from '../pages/TaxesPage'
import { page } from './fixtures'

const IVA: Tax = {
  id: 'tax-iva',
  code: 'IVA',
  name: 'IVA 19% alojamiento',
  rate: '19.00',
  applies_to: 'room',
  included_in_price: false,
  exempt_foreign_non_residents: true,
  is_active: true,
}

function mockTaxes(initial: Tax[] = [IVA]) {
  let taxes = [...initial]
  const requests: { method: string; url: string; body?: unknown }[] = []
  server.use(
    http.get('/api/v1/rates/taxes/', () => HttpResponse.json(page(taxes))),
    http.post('/api/v1/rates/taxes/', async ({ request }) => {
      const body = (await request.json()) as Omit<Tax, 'id'>
      requests.push({ method: 'POST', url: request.url, body })
      const created = { ...body, id: 'tax-new' } as Tax
      taxes = [...taxes, created]
      return HttpResponse.json(created, { status: 201 })
    }),
    http.patch('/api/v1/rates/taxes/:id/', async ({ request, params }) => {
      const body = (await request.json()) as Partial<Tax>
      requests.push({ method: 'PATCH', url: request.url, body })
      taxes = taxes.map((tax) => (tax.id === params.id ? { ...tax, ...body } : tax))
      return HttpResponse.json(taxes.find((tax) => tax.id === params.id))
    }),
    http.delete('/api/v1/rates/taxes/:id/', () =>
      HttpResponse.json({ detail: 'Está en uso: desactívalo en lugar de eliminarlo', code: 'in_use' }, { status: 409 }),
    ),
  )
  return requests
}

beforeEach(() => {
  document.cookie = 'csrftoken=t; path=/'
  useSession.setState({ propertyId: auroraProperty.id, loggedOut: false })
  mockMe(makeMe())
})

describe('taxes settings', () => {
  it('lists the taxes with what each one applies to', async () => {
    mockTaxes()
    renderWithProviders(<TaxesPage />)

    const row = (await screen.findByText('IVA 19% alojamiento')).closest('tr')!
    expect(within(row).getByText('19 %')).toBeInTheDocument()
    expect(within(row).getByText('Alojamiento')).toBeInTheDocument()
    expect(within(row).getByText('Exento para extranjeros')).toBeInTheDocument()
  })

  it('creates a tax', async () => {
    const requests = mockTaxes()
    const { user } = renderWithProviders(<TaxesPage />)

    await user.click(await screen.findByRole('button', { name: 'Nuevo impuesto' }))
    const dialog = await screen.findByRole('dialog', { name: 'Nuevo impuesto' })
    await user.type(within(dialog).getByLabelText('Código'), 'ICA')
    await user.type(within(dialog).getByLabelText('Nombre'), 'Impuesto municipal')
    await user.type(within(dialog).getByLabelText('Tarifa (%)'), '1,5')
    await user.click(within(dialog).getByRole('combobox', { name: 'Aplica a' }))
    await user.click(await screen.findByRole('option', { name: 'Todo' }))
    await user.click(within(dialog).getByRole('switch', { name: 'Incluido en el precio' }))
    await user.click(within(dialog).getByRole('button', { name: 'Crear impuesto' }))

    await waitFor(() => expect(requests).toHaveLength(1))
    expect(requests[0].body).toEqual({
      code: 'ICA',
      name: 'Impuesto municipal',
      rate: '1.5',
      applies_to: 'all',
      included_in_price: true,
      exempt_foreign_non_residents: false,
      is_active: true,
    })
    expect(await screen.findByText('Impuesto creado')).toBeInTheDocument()
    expect(await screen.findByText('Impuesto municipal')).toBeInTheDocument()
    expect(screen.queryByRole('dialog', { name: 'Nuevo impuesto' })).not.toBeInTheDocument()
  })

  it('shows the reason of a rejected code next to the field', async () => {
    mockTaxes()
    server.use(
      http.post('/api/v1/rates/taxes/', () =>
        HttpResponse.json(
          {
            detail: 'Ya existe un registro con este código en la propiedad',
            code: 'validation_error',
            fields: { code: ['Ya existe un registro con este código en la propiedad'] },
          },
          { status: 400 },
        ),
      ),
    )
    const { user } = renderWithProviders(<TaxesPage />)

    await user.click(await screen.findByRole('button', { name: 'Nuevo impuesto' }))
    const dialog = await screen.findByRole('dialog', { name: 'Nuevo impuesto' })
    await user.type(within(dialog).getByLabelText('Código'), 'IVA')
    await user.type(within(dialog).getByLabelText('Nombre'), 'Otro IVA')
    await user.type(within(dialog).getByLabelText('Tarifa (%)'), '19')
    await user.click(within(dialog).getByRole('button', { name: 'Crear impuesto' }))

    expect(await within(dialog).findByText('Ya existe un registro con este código en la propiedad')).toBeInTheDocument()
    expect(within(dialog).getByLabelText('Código')).toHaveAttribute('aria-invalid', 'true')
  })

  it('validates the rate before sending', async () => {
    const requests = mockTaxes()
    const { user } = renderWithProviders(<TaxesPage />)

    await user.click(await screen.findByRole('button', { name: 'Nuevo impuesto' }))
    const dialog = await screen.findByRole('dialog', { name: 'Nuevo impuesto' })
    await user.type(within(dialog).getByLabelText('Código'), 'X')
    await user.type(within(dialog).getByLabelText('Nombre'), 'X')
    await user.type(within(dialog).getByLabelText('Tarifa (%)'), '120')
    await user.click(within(dialog).getByRole('button', { name: 'Crear impuesto' }))

    expect(await within(dialog).findByText('Escribe un porcentaje entre 0 y 100.')).toBeInTheDocument()
    expect(requests).toHaveLength(0)
  })

  it('edits a tax', async () => {
    const requests = mockTaxes()
    const { user } = renderWithProviders(<TaxesPage />)

    await user.click(await screen.findByRole('button', { name: 'Editar IVA 19% alojamiento' }))
    const dialog = await screen.findByRole('dialog', { name: 'Editar impuesto' })
    expect(within(dialog).getByLabelText('Tarifa (%)')).toHaveValue('19')
    await user.click(within(dialog).getByRole('switch', { name: 'Activo' }))
    await user.click(within(dialog).getByRole('button', { name: 'Guardar cambios' }))

    await waitFor(() => expect(requests).toHaveLength(1))
    expect(requests[0]).toMatchObject({ method: 'PATCH', body: { is_active: false, code: 'IVA' } })
    expect(requests[0].url).toMatch(/\/rates\/taxes\/tax-iva\/$/)
  })

  it('explains why a tax in use cannot be deleted', async () => {
    mockTaxes()
    const { user } = renderWithProviders(<TaxesPage />)

    await user.click(await screen.findByRole('button', { name: 'Eliminar IVA 19% alojamiento' }))
    const dialog = await screen.findByRole('dialog', { name: '¿Eliminar IVA 19% alojamiento?' })
    await user.click(within(dialog).getByRole('button', { name: 'Eliminar' }))

    expect(await within(dialog).findByRole('alert')).toHaveTextContent('Está en uso: desactívalo en lugar de eliminarlo')
  })
})
