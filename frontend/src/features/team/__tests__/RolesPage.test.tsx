import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import { useSession } from '@/lib/session'
import { auroraMembership, makeMe, mockMe } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import type { PermissionModule, Role } from '../api'
import RolesPage from '../pages/RolesPage'
import { makeRole, ownerRole } from './fixtures'

const catalog: PermissionModule[] = [
  {
    code: 'bookings',
    label_es: 'Reservas',
    label_en: 'Reservations',
    permissions: [
      { code: 'bookings.view', label_es: 'Ver reservas', label_en: 'View reservations' },
      { code: 'bookings.checkin', label_es: 'Hacer check-in y check-out', label_en: 'Check guests in and out' },
    ],
  },
  {
    code: 'guests',
    label_es: 'Huéspedes',
    label_en: 'Guests',
    permissions: [{ code: 'guests.view', label_es: 'Ver huéspedes', label_en: 'View guests' }],
  },
]

const night = makeRole({
  id: 'role-night',
  code: 'recepcion_nocturna',
  name: 'Recepción nocturna',
  is_system: false,
  editable: true,
  permissions: ['bookings.view'],
  members_count: 0,
  description: 'Turno de noche',
})

function useRoleHandlers(roles: Role[] = [ownerRole, makeRole(), night]) {
  server.use(
    http.get('/api/v1/accounts/roles/', () => HttpResponse.json(roles)),
    http.get('/api/v1/accounts/permissions/', () => HttpResponse.json(catalog)),
  )
}

beforeEach(() => {
  document.cookie = 'csrftoken=t; path=/'
  useSession.setState({ propertyId: null, loggedOut: false })
  mockMe(makeMe({ memberships: [auroraMembership(['*'], 'owner')] }))
})

describe('RolesPage', () => {
  it('lists Housetel templates and your roles, with how much each one can reach', async () => {
    useRoleHandlers()
    renderWithProviders(<RolesPage />)

    const list = await screen.findByRole('navigation', { name: 'Roles' })
    expect(within(list).getByRole('button', { name: /Recepción nocturna/ })).toBeInTheDocument()
    expect(within(list).getByRole('button', { name: /Dueño/ })).toBeInTheDocument()
    expect(within(list).getByRole('img', { name: 'Recepción nocturna: acceso a 1 de 2 módulos' })).toBeInTheDocument()
  })

  it('edits a custom role with the permission matrix', async () => {
    useRoleHandlers()
    let body: unknown = null
    server.use(
      http.patch('/api/v1/accounts/roles/role-night/', async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({ ...night, permissions: ['bookings.checkin', 'bookings.view'] })
      }),
    )
    const { user } = renderWithProviders(<RolesPage />)
    await user.click(await screen.findByRole('button', { name: /Recepción nocturna/ }))

    await user.click(await screen.findByRole('checkbox', { name: /Hacer check-in y check-out/ }))
    await user.click(screen.getByRole('button', { name: 'Guardar rol' }))

    await waitFor(() =>
      expect(body).toEqual({ name: 'Recepción nocturna', description: 'Turno de noche', permissions: ['bookings.checkin', 'bookings.view'] }),
    )
  })

  it('names every control of the role form, including the hidden inputs behind the checkboxes', async () => {
    useRoleHandlers()
    const { user } = renderWithProviders(<RolesPage />)
    await user.click(await screen.findByRole('button', { name: /Recepción nocturna/ }))

    const form = (await screen.findByRole('textbox', { name: 'Nombre del rol' })).closest('form')
    const controls = [...(form?.querySelectorAll('input, select, textarea') ?? [])]
    expect(controls.length).toBeGreaterThan(4)
    // Browsers flag unnamed controls (autofill cannot map them).
    expect(controls.filter((control) => !control.id && !control.getAttribute('name'))).toEqual([])
  })

  it('keeps templates read-only and duplicates them into an editable role', async () => {
    useRoleHandlers()
    const copy = makeRole({ id: 'role-copy', code: 'copia_de_recepcion', name: 'Copia de Recepción', is_system: false, editable: true })
    server.use(
      http.post('/api/v1/accounts/roles/role-front/duplicate/', () => {
        useRoleHandlers([ownerRole, makeRole(), night, copy])
        return HttpResponse.json(copy, { status: 201 })
      }),
    )
    const { user } = renderWithProviders(<RolesPage />)
    await user.click(await screen.findByRole('button', { name: /^Recepción\b(?! nocturna)/ }))

    expect(await screen.findByText('Las plantillas de Housetel no se editan: duplícala para ajustarla a tu hotel.')).toBeInTheDocument()
    for (const checkbox of screen.getAllByRole('checkbox')) expect(checkbox).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Duplicar' }))

    expect(await screen.findByRole('textbox', { name: 'Nombre del rol' })).toHaveValue('Copia de Recepción')
  })

  it('creates a role from scratch', async () => {
    useRoleHandlers()
    let body: unknown = null
    server.use(
      http.post('/api/v1/accounts/roles/', async ({ request }) => {
        body = await request.json()
        return HttpResponse.json(makeRole({ id: 'role-audit', name: 'Auditoría', is_system: false, editable: true }), { status: 201 })
      }),
    )
    const { user } = renderWithProviders(<RolesPage />)
    await user.click(await screen.findByRole('button', { name: 'Nuevo rol' }))

    await user.type(screen.getByRole('textbox', { name: 'Nombre del rol' }), 'Auditoría')
    await user.click(screen.getByRole('checkbox', { name: 'Todos los permisos de Huéspedes' }))
    await user.click(screen.getByRole('button', { name: 'Crear rol' }))

    await waitFor(() => expect(body).toEqual({ name: 'Auditoría', description: '', permissions: ['guests.view'] }))
  })
})
