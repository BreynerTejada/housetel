import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '@/lib/api'
import { useSession } from '@/lib/session'
import { auroraMembership, makeMe, mockMe } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import type { GuestDocument } from '../api'
import GuestDetailPage from '../pages/GuestDetailPage'
import { makeDuplicate, makeGuest, page } from './fixtures'

const ana = makeGuest({ email: '', is_vip: true })
const duplicate = makeDuplicate({ email: 'ana.vieja@example.com', reasons: ['document', 'phone_name'] })

function useGuestHandlers({ guest = ana, duplicates = [duplicate], documents = [] as GuestDocument[] } = {}) {
  server.use(
    http.get(`/api/v1/guests/guests/${guest.id}/`, () => HttpResponse.json(guest)),
    http.get(`/api/v1/guests/guests/${guest.id}/duplicates/`, () => HttpResponse.json(duplicates)),
    http.get(`/api/v1/guests/guests/${guest.id}/documents/`, () => HttpResponse.json(documents)),
    http.get(`/api/v1/guests/guests/${guest.id}/stays/`, () => HttpResponse.json(page([]))),
    http.get('/api/v1/guests/guests/tags/', () => HttpResponse.json([])),
  )
}

function renderDetail(id = 'guest-ana') {
  return renderWithProviders(<GuestDetailPage />, { route: `/app/guests/${id}`, path: '/app/guests/:id' })
}

beforeEach(() => {
  document.cookie = 'csrftoken=t; path=/'
  useSession.setState({ propertyId: null, loggedOut: false })
  mockMe(makeMe())
  // jsdom has no object URLs; the private previews use them.
  URL.createObjectURL = vi.fn(() => 'blob:preview')
  URL.revokeObjectURL = vi.fn()
})

describe('GuestDetailPage', () => {
  it('shows the registration card, stats and the Habeas Data consent', async () => {
    useGuestHandlers({ duplicates: [] })
    renderDetail()

    expect(await screen.findByRole('heading', { name: 'Ana María Pérez Gómez', level: 1 })).toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: 'Ruta de navegación' })).toBeInTheDocument()
    const card = screen.getByRole('region', { name: 'Ficha de registro' })
    expect(within(card).getByText('CC 52.123.456')).toBeInTheDocument()
    expect(within(card).getAllByText('Colombia').length).toBeGreaterThan(0)
    expect(within(card).getByText('VIP')).toBeInTheDocument()
    expect(screen.getByText('$ 2.450.000')).toBeInTheDocument()
    expect(screen.getByText('Autorizó el 12 mar 2025')).toBeInTheDocument()
  })

  it('merges a duplicate after comparing both profiles side by side', async () => {
    useGuestHandlers()
    let body: unknown = null
    server.use(
      http.post('/api/v1/guests/guests/merge/', async ({ request }) => {
        body = await request.json()
        return HttpResponse.json(ana)
      }),
    )
    const { user } = renderDetail()

    expect(await screen.findByText('Encontramos 1 perfil que podría ser esta misma persona.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Revisar y fusionar' }))

    const dialog = await screen.findByRole('dialog', { name: 'Fusionar perfiles' })
    const emailRow = within(dialog).getByRole('row', { name: /Correo/ })
    expect(within(emailRow).getByText('se completa')).toBeInTheDocument()
    expect(within(emailRow).getAllByText('ana.vieja@example.com')).toHaveLength(2)
    await user.click(within(dialog).getByRole('button', { name: 'Fusionar perfiles' }))

    await waitFor(() => expect(body).toEqual({ primary_id: 'guest-ana', duplicate_id: 'guest-dup', confirm: true }))
  })

  it('can keep the other profile instead', async () => {
    useGuestHandlers()
    // after merging, the page opens the kept profile
    useGuestHandlers({ guest: makeGuest({ id: 'guest-dup', full_name: 'Ana Perez' }), duplicates: [] })
    let body: unknown = null
    server.use(
      http.post('/api/v1/guests/guests/merge/', async ({ request }) => {
        body = await request.json()
        return HttpResponse.json(makeGuest({ id: 'guest-dup' }))
      }),
    )
    const { user, router } = renderDetail()
    await user.click(await screen.findByRole('button', { name: 'Revisar y fusionar' }))
    const dialog = await screen.findByRole('dialog', { name: 'Fusionar perfiles' })

    await user.click(within(dialog).getByRole('button', { name: 'Intercambiar perfiles' }))
    await user.click(within(dialog).getByRole('button', { name: 'Fusionar perfiles' }))

    await waitFor(() => expect(body).toEqual({ primary_id: 'guest-dup', duplicate_id: 'guest-ana', confirm: true }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/app/guests/guest-dup'))
  })

  it('front desk sees the duplicates but cannot merge them', async () => {
    mockMe(makeMe({ memberships: [auroraMembership(['guests.view', 'guests.manage'], 'front_desk')] }))
    useGuestHandlers()
    renderDetail()

    expect(await screen.findByText('Pide a un gerente que los revise y los fusione.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Revisar y fusionar' })).not.toBeInTheDocument()
  })

  it('anonymizes only after typing the confirmation word', async () => {
    useGuestHandlers({ duplicates: [] })
    let body: unknown = null
    server.use(
      http.post('/api/v1/guests/guests/guest-ana/anonymize/', async ({ request }) => {
        body = await request.json()
        return HttpResponse.json(makeGuest({ full_name: 'Huésped anonimizado', anonymized_at: '2026-09-25T10:00:00-05:00' }))
      }),
    )
    const { user } = renderDetail()
    await user.click(await screen.findByRole('button', { name: 'Más acciones' }))
    await user.click(await screen.findByRole('menuitem', { name: 'Anonimizar datos' }))

    const dialog = await screen.findByRole('dialog', { name: /Anonimizar los datos de Ana María Pérez Gómez/ })
    const confirm = within(dialog).getByRole('button', { name: 'Anonimizar datos' })
    expect(confirm).toBeDisabled()
    await user.type(within(dialog).getByRole('textbox', { name: 'Texto de confirmación' }), 'ANONIMIZAR')
    await user.click(confirm)

    await waitFor(() => expect(body).toEqual({ confirm: true }))
  })

  it('says the stay history could not load instead of showing an empty history', async () => {
    useGuestHandlers({ duplicates: [] })
    server.use(
      http.get('/api/v1/guests/guests/guest-ana/stays/', () =>
        HttpResponse.json({ detail: 'El servidor no respondió', code: 'server_error' }, { status: 500 }),
      ),
    )
    const { user } = renderDetail()
    await user.click(await screen.findByRole('tab', { name: /Estancias/ }))

    const panel = screen.getByRole('tabpanel', { name: /Estancias/ })
    expect(await within(panel).findByRole('alert')).toBeInTheDocument()
    expect(within(panel).queryByText('Todavía no tiene reservas.')).not.toBeInTheDocument()
  })

  it('sends people from a merged profile to the main one', async () => {
    useGuestHandlers({ guest: makeGuest({ merged_into: 'guest-main' }), duplicates: [] })
    renderDetail()
    const link = await screen.findByRole('link', { name: 'Abrir el perfil principal' })
    expect(link).toHaveAttribute('href', '/app/guests/guest-main')
  })

  it('uploads identity documents and shows them through the private endpoint', async () => {
    const stored: GuestDocument = {
      id: 'doc-1',
      guest: 'guest-ana',
      kind: 'passport',
      uploaded_via: 'staff',
      created_at: '2026-09-25T10:00:00-05:00',
      file_url: '/api/v1/guests/documents/doc-1/file/',
      content_type: 'image/png',
      filename: 'passport-20260925.png',
      size: 2048,
    }
    useGuestHandlers({ duplicates: [] })
    const fileRequests: string[] = []
    server.use(
      http.get('/api/v1/guests/documents/doc-1/file/', ({ request }) => {
        fileRequests.push(request.url)
        return new HttpResponse(new Blob(['png'], { type: 'image/png' }), { headers: { 'Content-Type': 'image/png' } })
      }),
    )
    // jsdom's File cannot go through Node's fetch, so the upload is checked where it leaves the component:
    // the multipart body handed to the API client (multipart transport is covered by lib/api tests).
    let uploaded = null as { path: string; form?: FormData } | null
    const post = vi.spyOn(api, 'post').mockImplementation(async (path, _body, opts) => {
      uploaded = { path, form: opts?.formData }
      useGuestHandlers({ duplicates: [], documents: [stored] })
      return stored as never
    })
    const { user } = renderDetail()
    await user.click(await screen.findByRole('tab', { name: /Documentos/ }))

    const input = await screen.findByLabelText('Elegir archivo')
    await user.upload(input, new File(['png'], 'pasaporte.png', { type: 'image/png' }))

    await waitFor(() => expect(uploaded?.path).toBe('/guests/guests/guest-ana/documents/'))
    expect(uploaded?.form?.get('kind')).toBe('id_front')
    expect((uploaded?.form?.get('file') as File).name).toBe('pasaporte.png')
    expect(await screen.findByRole('img', { name: 'Pasaporte' })).toHaveAttribute('src', 'blob:preview')
    expect(fileRequests).toEqual([expect.stringContaining('/api/v1/guests/documents/doc-1/file/')])
    expect(document.body.innerHTML).not.toContain('/media/')
    post.mockRestore()
  })
})
