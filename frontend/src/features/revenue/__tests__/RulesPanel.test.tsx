import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import { useSession } from '@/lib/session'
import { auroraMembership, auroraProperty, makeMe, mockMe } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import { RulesPanel } from '../components/RulesPanel'
import { OPTIONS, RULES, TODAY } from './fixtures'

interface Log {
  created: unknown[]
  patched: { id: string; body: unknown }[]
  deleted: string[]
  simulated: unknown[]
}

function mockRulesApi(rules = RULES): Log {
  const log: Log = { created: [], patched: [], deleted: [], simulated: [] }
  let current = [...rules]
  server.use(
    http.get('/api/v1/revenue/rules/', () => HttpResponse.json(current)),
    http.get('/api/v1/revenue/options/', () => HttpResponse.json(OPTIONS)),
    http.post('/api/v1/revenue/rules/', async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>
      log.created.push(body)
      const rule = { ...RULES[0], ...body, id: 'rule-new' }
      current = [...current, rule as (typeof RULES)[number]]
      return HttpResponse.json(rule, { status: 201 })
    }),
    http.patch('/api/v1/revenue/rules/:id/', async ({ params, request }) => {
      const body = (await request.json()) as Record<string, unknown>
      log.patched.push({ id: String(params.id), body })
      current = current.map((rule) => (rule.id === params.id ? ({ ...rule, ...body } as typeof rule) : rule))
      return HttpResponse.json(current.find((rule) => rule.id === params.id))
    }),
    http.delete('/api/v1/revenue/rules/:id/', ({ params }) => {
      log.deleted.push(String(params.id))
      current = current.filter((rule) => rule.id !== params.id)
      return new HttpResponse(null, { status: 204 })
    }),
    http.post('/api/v1/revenue/simulate/', async ({ request }) => {
      log.simulated.push(await request.json())
      return HttpResponse.json({
        start: TODAY,
        end: '2027-01-23',
        summary: {
          count: 12,
          up: 9,
          down: 3,
          avg_change_percent: '7.50',
          estimated_impact: '2400000.00',
          impact_up: '2600000.00',
          impact_down: '-200000.00',
        },
        recommendations: [],
      })
    }),
  )
  return log
}

function renderPanel() {
  return renderWithProviders(<RulesPanel today={TODAY} />, { route: '/app/revenue?tab=rules' })
}

beforeEach(() => {
  document.cookie = 'csrftoken=t; path=/'
  useSession.setState({ propertyId: auroraProperty.id, loggedOut: false })
  mockMe(makeMe())
})

describe('rules', () => {
  it('lists each rule with a picture of what it does', async () => {
    mockRulesApi()
    renderPanel()

    const occupancy = await screen.findByRole('article', { name: 'Ocupación' })
    expect(within(occupancy).getByText('0–40 % → −8 %')).toBeInTheDocument()
    expect(within(occupancy).getByText('85–100 % → +15 %')).toBeInTheDocument()
    expect(within(occupancy).getByText('Todas las categorías')).toBeInTheDocument()
    expect(within(occupancy).getByText('Suma')).toBeInTheDocument()
    const saturdays = screen.getByRole('article', { name: 'Sábados' })
    expect(within(saturdays).getByText('Inactiva')).toBeInTheDocument()
    expect(within(saturdays).getByText('STE')).toBeInTheDocument() // only the suite
    expect(within(saturdays).getByLabelText('Sábado: +8 %')).toBeInTheDocument()
  })

  it('creates an occupancy rule from its tiers', async () => {
    const log = mockRulesApi()
    const { user } = renderPanel()

    await user.click(await screen.findByRole('button', { name: 'Nueva regla' }))
    const editor = await screen.findByRole('dialog', { name: 'Nueva regla' })
    await user.type(within(editor).getByLabelText('Nombre'), 'Ocupación alta')
    const lastTier = within(editor).getByRole('group', { name: 'Tramo 3' })
    const adjust = within(lastTier).getByLabelText('Ajuste (%)')
    await user.clear(adjust)
    await user.type(adjust, '20')
    await user.click(within(editor).getByRole('button', { name: 'Crear regla' }))

    await waitFor(() => expect(log.created).toHaveLength(1))
    expect(log.created[0]).toEqual({
      name: 'Ocupación alta',
      kind: 'occupancy',
      room_types: [],
      combine: 'stack',
      priority: 10,
      is_active: true,
      params: {
        tiers: [
          { min: 0, max: 40, adjust: -8 },
          { min: 70, max: 85, adjust: 8 },
          { min: 85, max: 100, adjust: 20 },
        ],
      },
    })
    expect(await screen.findByText('Regla guardada')).toBeInTheDocument()
  })

  it('points at the tier that overlaps and sends nothing until it is fixed', async () => {
    const log = mockRulesApi()
    const { user } = renderPanel()

    await user.click(await screen.findByRole('button', { name: 'Nueva regla' }))
    const editor = await screen.findByRole('dialog', { name: 'Nueva regla' })
    await user.type(within(editor).getByLabelText('Nombre'), 'Cruzada')
    const second = within(editor).getByRole('group', { name: 'Tramo 2' })
    const from = within(second).getByLabelText('Desde (%)')
    await user.clear(from)
    await user.type(from, '30')
    await user.click(within(editor).getByRole('button', { name: 'Crear regla' }))

    expect(await within(editor).findByText('Se cruza con otro tramo')).toBeInTheDocument()
    expect(from).toHaveAttribute('aria-invalid', 'true')
    expect(log.created).toHaveLength(0)
  })

  it('builds a weekday rule for some categories and combines it as a maximum', async () => {
    const log = mockRulesApi()
    const { user } = renderPanel()

    await user.click(await screen.findByRole('button', { name: 'Nueva regla' }))
    const editor = await screen.findByRole('dialog', { name: 'Nueva regla' })
    await user.type(within(editor).getByLabelText('Nombre'), 'Viernes')
    await user.click(within(editor).getByRole('radio', { name: /Día de la semana/ }))
    const saturday = within(editor).getByLabelText('Ajuste del sábado (%)')
    await user.clear(saturday)
    await user.type(within(editor).getByLabelText('Ajuste del viernes (%)'), '6')
    await user.click(within(editor).getByRole('switch', { name: 'Todas las categorías' }))
    await user.click(within(editor).getByRole('checkbox', { name: 'Suite Vista al Mar' }))
    await user.click(within(editor).getByRole('radio', { name: /Máximo/ }))
    await user.click(within(editor).getByRole('button', { name: 'Crear regla' }))

    await waitFor(() => expect(log.created).toHaveLength(1))
    expect(log.created[0]).toMatchObject({
      kind: 'day_of_week',
      room_types: ['rt-ste'],
      combine: 'max',
      params: { fri: 6 },
    })
  })

  it('previews what a run would leave with the draft, without saving it', async () => {
    const log = mockRulesApi()
    const { user } = renderPanel()

    await user.click(await screen.findByRole('button', { name: 'Editar «Ocupación»' }))
    const editor = await screen.findByRole('dialog', { name: 'Editar regla' })
    await user.click(within(editor).getByRole('button', { name: 'Probar con los datos de hoy' }))

    expect(await within(editor).findByText(/Una corrida ahora dejaría 12 recomendaciones \(9 suben · 3 bajan\)/)).toBeInTheDocument()
    expect(log.simulated).toEqual([
      {
        rule: {
          id: 'rule-occ',
          name: 'Ocupación',
          kind: 'occupancy',
          room_types: [],
          combine: 'stack',
          priority: 40,
          is_active: true,
          params: RULES[0].params,
        },
      },
    ])
    expect(log.patched).toHaveLength(0)
  })

  it('shows what the server rejected next to the builder', async () => {
    mockRulesApi()
    server.use(
      http.post('/api/v1/revenue/rules/', () =>
        HttpResponse.json(
          { detail: 'Los tramos de ocupación no pueden solaparse', code: 'invalid_rule_params', fields: { params: ['Los tramos de ocupación no pueden solaparse'] } },
          { status: 400 },
        ),
      ),
    )
    const { user } = renderPanel()

    await user.click(await screen.findByRole('button', { name: 'Nueva regla' }))
    const editor = await screen.findByRole('dialog', { name: 'Nueva regla' })
    await user.type(within(editor).getByLabelText('Nombre'), 'Ocupación')
    await user.click(within(editor).getByRole('button', { name: 'Crear regla' }))
    expect(await within(editor).findByText('Los tramos de ocupación no pueden solaparse')).toBeInTheDocument()
  })

  it('turns a rule on from its card and deletes another after confirming', async () => {
    const log = mockRulesApi()
    const { user } = renderPanel()

    const toggle = await screen.findByRole('switch', { name: 'Regla «Sábados» activa' })
    await waitFor(() => expect(toggle).toBeEnabled()) // once the permissions of the user are known
    await user.click(toggle)
    await waitFor(() => expect(log.patched).toEqual([{ id: 'rule-sat', body: { is_active: true } }]))

    await user.click(screen.getByRole('button', { name: 'Eliminar «Ocupación»' }))
    const dialog = await screen.findByRole('dialog', { name: '¿Eliminar la regla «Ocupación»?' })
    await user.click(within(dialog).getByRole('button', { name: 'Eliminar regla' }))
    await waitFor(() => expect(log.deleted).toEqual(['rule-occ']))
    await waitFor(() => expect(screen.queryByRole('article', { name: 'Ocupación' })).not.toBeInTheDocument())
  })

  it('is read-only without revenue.manage', async () => {
    mockMe(makeMe({ memberships: [auroraMembership(['revenue.view'], 'front_desk')] }))
    mockRulesApi()
    const { queryClient } = renderPanel()

    await waitFor(() => expect(queryClient.getQueryData(['me'])).toBeTruthy()) // permissions known
    expect(await screen.findByRole('article', { name: 'Ocupación' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Nueva regla' })).not.toBeInTheDocument()
    expect(screen.getByRole('switch', { name: 'Regla «Sábados» activa' })).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'Eliminar «Ocupación»' })).not.toBeInTheDocument()
  })
})
