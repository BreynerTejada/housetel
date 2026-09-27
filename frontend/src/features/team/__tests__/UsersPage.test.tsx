import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useSession } from '@/lib/session'
import { auroraMembership, auroraProperty, makeMe, mockMe } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import UsersPage from '../pages/UsersPage'
import { makeInvitation, makeMember, makeRole, ownerRole } from './fixtures'

const secondHotel = { ...auroraProperty, id: 'prop-2', name: 'Aurora Playa', slug: 'aurora-playa' }

beforeEach(() => {
  document.cookie = 'csrftoken=t; path=/'
  useSession.setState({ propertyId: null, loggedOut: false })
  const membership = auroraMembership(['*'], 'owner')
  mockMe(makeMe({ memberships: [{ ...membership, properties: [auroraProperty, secondHotel] }] }))
  server.use(
    http.get('/api/v1/accounts/users/', () =>
      HttpResponse.json({
        count: 2,
        next: null,
        previous: null,
        results: [
          makeMember({
            id: 'member-me',
            user: { id: 'user-1', email: 'owner@casaaurora.co', full_name: 'Valentina Ríos', phone: '', last_login: '2026-09-25T08:00:00-05:00' },
            role: { id: 'role-owner', code: 'owner', name: 'Dueño', is_system: true },
            is_owner: true,
            is_self: true,
          }),
          makeMember(),
        ],
      }),
    ),
    http.get('/api/v1/accounts/invitations/', () => HttpResponse.json([makeInvitation()])),
    http.get('/api/v1/accounts/roles/', () =>
      HttpResponse.json([ownerRole, makeRole(), makeRole({ id: 'role-billing', code: 'billing_admin', name: 'Facturación Housetel', assignable: false })]),
    ),
  )
})

describe('UsersPage', () => {
  it('lists the team and the pending invitations', async () => {
    renderWithProviders(<UsersPage />)

    const me = await screen.findByRole('row', { name: /Valentina Ríos/ })
    expect(within(me).getByText('Tú')).toBeInTheDocument()
    const clerk = screen.getByRole('row', { name: /Andrés Gómez/ })
    expect(within(clerk).getByText('Recepción')).toBeInTheDocument()
    expect(within(clerk).getByText('Todos los hoteles')).toBeInTheDocument()
    const invitations = screen.getByRole('region', { name: 'Invitaciones pendientes' })
    expect(within(invitations).getByText('nocturno@casaaurora.co')).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'Acciones' })).toBeInTheDocument()
  })

  it('invites someone to some hotels with a role they are allowed to assign', async () => {
    const warn = vi.spyOn(console, 'warn')
    let body: unknown = null
    server.use(
      http.post('/api/v1/accounts/users/', async ({ request }) => {
        body = await request.json()
        return HttpResponse.json(makeInvitation({ email: 'nueva@hotel.co', email_sent: true }), { status: 201 })
      }),
    )
    const { user } = renderWithProviders(<UsersPage />)
    await user.click(await screen.findByRole('button', { name: 'Invitar persona' }))
    const dialog = await screen.findByRole('dialog', { name: 'Invitar a tu equipo' })

    await user.type(within(dialog).getByRole('textbox', { name: 'Correo' }), 'nueva@hotel.co')
    await user.click(within(dialog).getByRole('combobox', { name: 'Rol' }))
    expect(await screen.findByRole('option', { name: /Facturación Housetel/ })).toHaveAttribute('aria-disabled', 'true')
    await user.click(screen.getByRole('option', { name: /Recepción/ }))
    await user.click(within(dialog).getByRole('radio', { name: 'Solo algunos hoteles' }))
    await user.click(within(dialog).getByRole('checkbox', { name: 'Aurora Playa' }))
    await user.click(within(dialog).getByRole('button', { name: 'Enviar invitación' }))

    await waitFor(() =>
      expect(body).toEqual({ email: 'nueva@hotel.co', role_id: 'role-front', all_properties: false, property_ids: ['prop-2'] }),
    )
    // the role select stays controlled from the first render
    expect(warn).not.toHaveBeenCalledWith(expect.stringContaining('uncontrolled to controlled'))
    warn.mockRestore()
  })

  it('shows the link to share by hand when the email could not be sent', async () => {
    server.use(
      http.post('/api/v1/accounts/users/', () =>
        HttpResponse.json(makeInvitation({ email: 'nueva@hotel.co', email_sent: false, invite_url: 'http://localhost:5173/invite/tok-999' }), {
          status: 201,
        }),
      ),
    )
    const { user } = renderWithProviders(<UsersPage />)
    await user.click(await screen.findByRole('button', { name: 'Invitar persona' }))
    const dialog = await screen.findByRole('dialog', { name: 'Invitar a tu equipo' })
    await user.type(within(dialog).getByRole('textbox', { name: 'Correo' }), 'nueva@hotel.co')
    await user.click(within(dialog).getByRole('combobox', { name: 'Rol' }))
    await user.click(await screen.findByRole('option', { name: /Recepción/ }))
    await user.click(within(dialog).getByRole('button', { name: 'Enviar invitación' }))

    expect(await within(dialog).findByText('No pudimos enviar el correo. Copia el enlace y compártelo por otro medio.')).toBeInTheDocument()
    expect(within(dialog).getByRole('textbox', { name: 'Enlace de la invitación' })).toHaveValue('http://localhost:5173/invite/tok-999')
  })

  it('deactivates a member after confirming', async () => {
    let body: unknown = null
    server.use(
      http.patch('/api/v1/accounts/users/member-andres/', async ({ request }) => {
        body = await request.json()
        return HttpResponse.json(makeMember({ is_active: false }))
      }),
    )
    const { user } = renderWithProviders(<UsersPage />)
    await user.click(await screen.findByRole('button', { name: 'Acciones de Andrés Gómez' }))
    await user.click(await screen.findByRole('menuitem', { name: 'Desactivar acceso' }))
    const dialog = await screen.findByRole('dialog', { name: '¿Desactivar el acceso de Andrés Gómez?' })
    await user.click(within(dialog).getByRole('button', { name: 'Desactivar acceso' }))

    await waitFor(() => expect(body).toEqual({ is_active: false }))
  })

  it('only lets someone restricted to some hotels invite to those hotels', async () => {
    const restricted = { ...auroraMembership(['accounts.users_manage', 'guests.*'], 'manager'), properties: [secondHotel] }
    mockMe(makeMe({ memberships: [restricted] }))
    server.use(
      http.get('/api/v1/accounts/users/', () =>
        HttpResponse.json({
          count: 1,
          next: null,
          previous: null,
          results: [
            makeMember({
              id: 'member-me',
              is_self: true,
              all_properties: false,
              properties: [{ id: secondHotel.id, name: secondHotel.name }],
            }),
          ],
        }),
      ),
    )
    const { user } = renderWithProviders(<UsersPage />)
    await screen.findByRole('row', { name: /Andrés Gómez/ })
    await user.click(screen.getByRole('button', { name: 'Invitar persona' }))
    const dialog = await screen.findByRole('dialog', { name: 'Invitar a tu equipo' })

    expect(within(dialog).getByRole('radio', { name: /Todos los hoteles de la organización/ })).toBeDisabled()
    expect(within(dialog).getByText('Solo puedes dar acceso a los hoteles donde tú trabajas.')).toBeInTheDocument()
    // their only hotel comes preselected
    expect(within(dialog).getByRole('radio', { name: 'Solo algunos hoteles' })).toBeChecked()
    expect(within(dialog).getByRole('checkbox', { name: 'Aurora Playa' })).toBeChecked()
    expect(within(dialog).queryByRole('checkbox', { name: 'Hotel Casa Aurora' })).not.toBeInTheDocument()
  })

  it('names every control of the invitation form', async () => {
    const { user } = renderWithProviders(<UsersPage />)
    await user.click(await screen.findByRole('button', { name: 'Invitar persona' }))
    const dialog = await screen.findByRole('dialog', { name: 'Invitar a tu equipo' })
    await user.click(within(dialog).getByRole('radio', { name: 'Solo algunos hoteles' }))

    const controls = [...dialog.querySelectorAll('input, select, textarea')]
    expect(controls.length).toBeGreaterThan(3)
    expect(controls.filter((control) => !control.id && !control.getAttribute('name'))).toEqual([])
  })

  it('locks invitations that hand out more than you can: no link, no resend, no revoke', async () => {
    server.use(
      http.get('/api/v1/accounts/invitations/', () =>
        HttpResponse.json([
          makeInvitation({ editable: false, invite_url: null, role: { id: 'role-owner', code: 'owner', name: 'Dueño', is_system: true } }),
        ]),
      ),
    )
    renderWithProviders(<UsersPage />)

    const invitations = await screen.findByRole('region', { name: 'Invitaciones pendientes' })
    expect(within(invitations).getByText('nocturno@casaaurora.co')).toBeInTheDocument()
    for (const action of ['Copiar enlace', 'Reenviar', 'Revocar']) {
      expect(within(invitations).queryByRole('button', { name: action })).not.toBeInTheDocument()
    }
    expect(within(invitations).getByLabelText(/solo alguien con más acceso puede reenviarla o revocarla/)).toBeInTheDocument()
  })

  it('does not offer changes on your own row', async () => {
    renderWithProviders(<UsersPage />)
    await screen.findByRole('row', { name: /Valentina Ríos/ })
    expect(screen.queryByRole('button', { name: 'Acciones de Valentina Ríos' })).not.toBeInTheDocument()
  })
})
