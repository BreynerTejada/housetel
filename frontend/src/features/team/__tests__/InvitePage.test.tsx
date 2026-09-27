import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import { ME_QUERY_KEY, type Me } from '@/lib/auth'
import { useSession } from '@/lib/session'
import { makeMe, mockMe } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import type { PublicInvitation } from '../api'
import InvitePage from '../pages/InvitePage'

const URL = '/api/v1/public/accounts/invitations/tok-123/'

function makeInvitation(overrides: Partial<PublicInvitation> = {}): PublicInvitation {
  return {
    email: 'nueva@hotel.co',
    organization: { name: 'Casa Aurora' },
    role: { name: 'Recepción nocturna', code: 'recepcion_nocturna' },
    properties: ['Hotel Casa Aurora'],
    all_properties: false,
    invited_by: 'Valentina Ríos',
    expires_at: '2026-10-02T10:00:00-05:00',
    status: 'pending',
    user_exists: false,
    ...overrides,
  }
}

function useInvitation(invitation: PublicInvitation | null) {
  server.use(
    http.get(URL, () =>
      invitation
        ? HttpResponse.json(invitation)
        : HttpResponse.json({ detail: 'Invitación no encontrada', code: 'not_found' }, { status: 404 }),
    ),
  )
}

function renderInvite() {
  return renderWithProviders(<InvitePage />, {
    route: '/invite/tok-123',
    path: '/invite/:token',
    routes: [
      { path: '/app', element: <p>app de recepción</p> },
      { path: '/login', element: <p>pantalla de ingreso</p> },
    ],
  })
}

const joined: Me = makeMe({ email: 'nueva@hotel.co', full_name: 'Nueva Recepcionista' })

beforeEach(() => {
  document.cookie = 'csrftoken=t; path=/'
  useSession.setState({ propertyId: null, loggedOut: false })
  mockMe(null)
})

describe('InvitePage', () => {
  it('shows who invites you, to which organization, with which role and hotels', async () => {
    useInvitation(makeInvitation())
    renderInvite()

    expect(await screen.findByRole('heading', { name: 'Únete a Casa Aurora', level: 1 })).toBeInTheDocument()
    const tag = screen.getByRole('group', { name: 'Tu acceso a Casa Aurora' })
    expect(within(tag).getByText('Recepción nocturna')).toBeInTheDocument()
    expect(within(tag).getByText('Hotel Casa Aurora')).toBeInTheDocument()
    expect(screen.getByText('Valentina Ríos te invitó con el rol Recepción nocturna.')).toBeInTheDocument()
    expect(screen.getByText('Crea tu cuenta para nueva@hotel.co.')).toBeInTheDocument()
  })

  it('creates the account, starts the session and opens the app', async () => {
    useInvitation(makeInvitation())
    let body: unknown = null
    server.use(
      http.post(`${URL}accept/`, async ({ request }) => {
        body = await request.json()
        return HttpResponse.json(joined)
      }),
    )
    const { user, router, queryClient } = renderInvite()

    await user.type(await screen.findByRole('textbox', { name: 'Tu nombre completo' }), 'Nueva Recepcionista')
    await user.type(screen.getByLabelText('Crea una contraseña'), 'Clave-segura-2026')
    await user.click(screen.getByRole('button', { name: 'Unirme a Casa Aurora' }))

    await waitFor(() => expect(router.state.location.pathname).toBe('/app'))
    expect(body).toEqual({ full_name: 'Nueva Recepcionista', password: 'Clave-segura-2026' })
    expect(queryClient.getQueryData(ME_QUERY_KEY)).toEqual(joined)
  })

  it('asks for a name and a password before sending', async () => {
    useInvitation(makeInvitation())
    const { user } = renderInvite()

    await user.click(await screen.findByRole('button', { name: 'Unirme a Casa Aurora' }))

    expect(await screen.findByText('Escribe tu nombre')).toBeInTheDocument()
    expect(screen.getByText('Crea una contraseña de al menos 8 caracteres')).toBeInTheDocument()
    expect(screen.queryByText(/Mínimo 8 caracteres/)).not.toBeInTheDocument() // the error replaces the hint
    expect(screen.getByRole('textbox', { name: 'Tu nombre completo' })).toHaveFocus()
  })

  it('shows the password rules the server did not accept', async () => {
    useInvitation(makeInvitation())
    server.use(
      http.post(`${URL}accept/`, () =>
        HttpResponse.json(
          {
            detail: 'Esta contraseña es demasiado común.',
            code: 'validation_error',
            fields: { password: ['Esta contraseña es demasiado común.'] },
          },
          { status: 400 },
        ),
      ),
    )
    const { user } = renderInvite()

    await user.type(await screen.findByRole('textbox', { name: 'Tu nombre completo' }), 'Nueva')
    await user.type(screen.getByLabelText('Crea una contraseña'), 'password123')
    await user.click(screen.getByRole('button', { name: 'Unirme a Casa Aurora' }))

    expect(await screen.findByText('Esta contraseña es demasiado común.')).toBeInTheDocument()
    expect(screen.getByLabelText('Crea una contraseña')).toHaveAttribute('aria-invalid', 'true')
  })

  it('lets an existing Housetel user join with their current password', async () => {
    useInvitation(makeInvitation({ user_exists: true }))
    let body: unknown = null
    server.use(
      http.post(`${URL}accept/`, async ({ request }) => {
        body = await request.json()
        return (body as { password: string }).password === 'mi-clave-actual'
          ? HttpResponse.json(joined)
          : HttpResponse.json(
              { detail: 'La contraseña no coincide con tu cuenta de Housetel', code: 'invalid_credentials' },
              { status: 400 },
            )
      }),
    )
    const { user, router } = renderInvite()

    expect(await screen.findByText('Ya tienes una cuenta en Housetel con nueva@hotel.co. Escribe tu contraseña para unirte.')).toBeInTheDocument()
    expect(screen.queryByRole('textbox', { name: 'Tu nombre completo' })).not.toBeInTheDocument()
    const password = screen.getByLabelText('Contraseña')
    await user.type(password, 'otra')
    await user.click(screen.getByRole('button', { name: 'Unirme a Casa Aurora' }))
    expect(await screen.findByText('La contraseña no coincide con tu cuenta de Housetel.')).toBeInTheDocument()

    await user.clear(password)
    await user.type(password, 'mi-clave-actual')
    await user.click(screen.getByRole('button', { name: 'Unirme a Casa Aurora' }))

    await waitFor(() => expect(router.state.location.pathname).toBe('/app'))
    expect(body).toEqual({ password: 'mi-clave-actual' })
  })

  it('warns when another account is signed in on this device', async () => {
    mockMe(makeMe({ email: 'owner@casaaurora.co' }))
    useInvitation(makeInvitation())
    renderInvite()

    expect(await screen.findByText('Tienes abierta la sesión de owner@casaaurora.co. Al unirte, entrarás como nueva@hotel.co.')).toBeInTheDocument()
  })

  it.each([
    [makeInvitation({ status: 'expired' }), 'Esta invitación venció', 'Pide a quien te invitó que te la reenvíe.'],
    [makeInvitation({ status: 'accepted' }), 'Esta invitación ya se usó', 'Si ya creaste tu cuenta, inicia sesión.'],
    [null, 'No encontramos esta invitación', 'Revisa que el enlace esté completo o pide una invitación nueva.'],
  ])('explains links that no longer work (%#)', async (invitation, title, text) => {
    useInvitation(invitation)
    renderInvite()

    expect(await screen.findByRole('heading', { name: title })).toBeInTheDocument()
    expect(screen.getByText(text)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Ir a iniciar sesión' })).toHaveAttribute('href', '/login')
    expect(screen.queryByRole('button', { name: /Unirme/ })).not.toBeInTheDocument()
  })
})
