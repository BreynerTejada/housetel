import { act, fireEvent, screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { publicApi } from '@/lib/api'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import type { CheckinPayload } from '../api'
import { goTo } from '../lib/navigation'
import CheckinPage from '../pages/CheckinPage'
import { makeCheckin, registeredCheckin, TOKEN } from './fixtures'

vi.mock('../lib/navigation', () => ({ goTo: vi.fn() }))

// jsdom has no canvas: a stand-in for signature_pad that the test can "draw" on.
const pads: { draw: () => void }[] = []
vi.mock('signature_pad', () => {
  class FakeSignaturePad {
    private empty = true
    private listeners: Record<string, (() => void)[]> = {}
    constructor() {
      pads.push(this)
    }
    addEventListener(type: string, listener: () => void) {
      ;(this.listeners[type] ??= []).push(listener)
    }
    removeEventListener() {}
    off() {}
    on() {}
    clear() {
      this.empty = true
    }
    isEmpty() {
      return this.empty
    }
    toData() {
      return []
    }
    fromData() {}
    toDataURL() {
      return 'data:image/png;base64,U0lHTkVE'
    }
    draw() {
      this.empty = false
      this.listeners.endStroke?.forEach((listener) => listener())
    }
  }
  return { default: FakeSignaturePad }
})

const BASE = `/api/v1/public/guestportal/${encodeURIComponent(TOKEN)}/`

interface Posted {
  url: string
  body: unknown
}

function serve(initial: CheckinPayload, handlers: { post?: (body: Record<string, unknown>) => CheckinPayload | Response } = {}) {
  const posts: Posted[] = []
  let current = initial
  server.use(
    http.get(`${BASE}checkin/`, () => HttpResponse.json(current)),
    http.post(`${BASE}checkin/`, async ({ request }) => {
      const isJson = (request.headers.get('Content-Type') ?? '').includes('json')
      const body = isJson ? ((await request.json()) as Record<string, unknown>) : Object.fromEntries((await request.formData()).entries())
      posts.push({ url: 'checkin/', body })
      const result = handlers.post?.(body) ?? current
      if (result instanceof Response) return result
      current = result
      return body.step === 'documents' && body.file ? HttpResponse.json({ document: { id: 'doc-new' }, checkin: current }, { status: 201 }) : HttpResponse.json(current)
    }),
    http.post(`${BASE}checkin/complete/`, () => {
      posts.push({ url: 'complete/', body: null })
      current = { ...current, status: 'completed', current_step: 'payment', completed_at: '2026-10-01T10:00:00-05:00', missing: [] }
      return HttpResponse.json(current)
    }),
    http.post(`${BASE}pay/`, () => {
      posts.push({ url: 'pay/', body: null })
      return HttpResponse.json({ reference: 'HT-7K2M9Q-AB12CD', checkout_url: 'http://localhost:5173/sim/pay/HT-7K2M9Q-AB12CD' }, { status: 201 })
    }),
  )
  return posts
}

function renderPage() {
  return renderWithProviders(<CheckinPage />, { route: `/g/${encodeURIComponent(TOKEN)}/checkin`, path: '/g/:token/checkin' })
}

beforeEach(() => {
  document.cookie = 'csrftoken=t; path=/'
  pads.length = 0
  vi.mocked(goTo).mockReset()
  localStorage.setItem('housetel.portal.lang:HT-7K2M9Q', '1')
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null)
})

function setDate(input: HTMLElement, value: string) {
  fireEvent.change(input, { target: { value } })
}

describe('CheckinPage — guests', () => {
  it('asks for every guest data before saving anything', async () => {
    const posts = serve(makeCheckin())
    const { user } = renderPage()

    expect(await screen.findByRole('heading', { name: '¿Quiénes se hospedan?' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Guardar y continuar' }))

    const companion = screen.getByRole('region', { name: 'Acompañante 1' })
    expect(within(companion).getByLabelText('Nombres')).toHaveAccessibleDescription('Este campo es obligatorio')
    expect(within(companion).getByLabelText('Número de documento')).toHaveAccessibleDescription('Este campo es obligatorio')
    const booker = screen.getByRole('region', { name: 'Titular de la reserva' })
    expect(within(booker).getByLabelText('Fecha de nacimiento')).toHaveAccessibleDescription('Este campo es obligatorio')
    expect(posts).toEqual([])
  })

  it('saves the booker and the companion and moves on to the documents', async () => {
    const posts = serve(makeCheckin(), { post: () => registeredCheckin() })
    const { user } = renderPage()

    const booker = await screen.findByRole('region', { name: 'Titular de la reserva' })
    setDate(within(booker).getByLabelText('Fecha de nacimiento'), '1990-04-02')
    const companion = screen.getByRole('region', { name: 'Acompañante 1' })
    await user.type(within(companion).getByLabelText('Nombres'), 'Ana María')
    await user.type(within(companion).getByLabelText('Apellidos'), 'Pérez')
    await user.type(within(companion).getByLabelText('Número de documento'), '1020304050')
    setDate(within(companion).getByLabelText('Fecha de nacimiento'), '1992-06-15')
    await user.click(screen.getByRole('button', { name: 'Guardar y continuar' }))

    expect(await screen.findByRole('heading', { name: 'Foto del documento' })).toBeInTheDocument()
    const body = posts[0]!.body as { step: string; guests: Record<string, unknown>[] }
    expect(body.step).toBe('guests')
    expect(body.guests[0]).toMatchObject({ role: 'booker', guest_id: 'guest-booker', birth_date: '1990-04-02', travel_reason: 'leisure', destination: 'Cartagena' })
    expect(body.guests[1]).toMatchObject({
      role: 'companion',
      guest_id: null,
      first_name: 'Ana María',
      last_name: 'Pérez',
      document_type: 'CC',
      document_number: '1020304050',
      nationality: 'CO',
      country_of_residence: 'CO',
      birth_date: '1992-06-15',
    })
  })

  it('shows the hotel answer when a document belongs to someone else', async () => {
    serve(registeredCheckin({ current_step: 'guests' }), {
      post: () => HttpResponse.json({ detail: 'Ese documento ya está registrado', code: 'document_in_use' }, { status: 409 }),
    })
    const { user } = renderPage()

    await user.click(await screen.findByRole('button', { name: 'Guardar y continuar' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Ese documento ya está registrado con otro nombre en el hotel')
  })
})

describe('CheckinPage — documents and arrival', () => {
  it('uploads the photo of each adult document and then continues', async () => {
    const withDocument = registeredCheckin()
    withDocument.guests[0]!.documents = [{ id: 'doc-new', kind: 'id_front', uploaded_via: 'portal', created_at: '2026-10-01T10:00:00-05:00' }]
    serve(registeredCheckin(), { post: () => registeredCheckin({ current_step: 'arrival' }) })
    // jsdom's File cannot go through Node's fetch: the multipart body is checked where it leaves the page
    // (multipart transport is covered by src/lib/__tests__/api.test.ts); JSON steps still go through MSW.
    const original = publicApi.post.bind(publicApi)
    let uploaded: { path: string; form?: FormData } | null = null
    const post = vi.spyOn(publicApi, 'post').mockImplementation(async (path, body, opts) => {
      if (!opts?.formData) return original(path, body, opts)
      uploaded = { path, form: opts.formData }
      return { document: { id: 'doc-new', kind: 'id_front', guest_id: 'guest-booker' }, checkin: withDocument } as never
    })
    const { user } = renderPage()

    const laura = await screen.findByRole('region', { name: 'Laura Gómez' })
    await user.upload(within(laura).getByLabelText('Tomar foto o subir archivo'), new File(['jpg'], 'cedula.jpg', { type: 'image/jpeg' }))

    expect(await within(laura).findByText('Documento (frente) recibido')).toBeInTheDocument()
    expect(uploaded!.path).toBe(`/guestportal/${encodeURIComponent(TOKEN)}/checkin/`)
    expect(Object.fromEntries(['step', 'guest_id', 'kind'].map((key) => [key, uploaded!.form!.get(key)]))).toEqual({
      step: 'documents',
      guest_id: 'guest-booker',
      kind: 'id_front',
    })
    expect((uploaded!.form!.get('file') as File).name).toBe('cedula.jpg')
    expect(within(screen.getByRole('region', { name: 'Ana Pérez' })).getByText('Falta la foto')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Continuar' }))
    expect(await screen.findByRole('heading', { name: '¿A qué hora llegas?' })).toBeInTheDocument()
    post.mockRestore()
  })

  it('saves the arrival time', async () => {
    const posts = serve(registeredCheckin({ current_step: 'arrival' }), { post: () => registeredCheckin({ current_step: 'signature', eta: '16:30' }) })
    const { user } = renderPage()

    fireEvent.change(await screen.findByLabelText('Hora estimada de llegada'), { target: { value: '16:30' } })
    await user.click(screen.getByRole('button', { name: 'Guardar y continuar' }))

    expect(await screen.findByRole('heading', { name: 'Firma y términos' })).toBeInTheDocument()
    expect(posts[0]!.body).toEqual({ step: 'arrival', eta: '16:30' })
  })
})

describe('CheckinPage — signature', () => {
  const atSignature = () => registeredCheckin({ current_step: 'signature', eta: '16:30', missing: [{ code: 'signature' }] })

  it('does not finish without a signature and without accepting the terms', async () => {
    const posts = serve(atSignature())
    const { user } = renderPage()

    await user.click(await screen.findByRole('button', { name: 'Firmar y terminar' }))

    expect(await screen.findByText('Firma dentro del recuadro para continuar.')).toBeInTheDocument()
    expect(screen.getByText('Acepta los términos para continuar.')).toBeInTheDocument()
    expect(posts).toEqual([])
  })

  it('signs, completes the check-in and offers to pay the balance', async () => {
    const posts = serve(atSignature(), { post: () => ({ ...atSignature(), current_step: 'payment', signature: { signed: true, accepted_terms_at: 'now' }, missing: [] }) })
    const { user } = renderPage()

    await screen.findByRole('heading', { name: 'Firma y términos' })
    act(() => pads[0]!.draw())
    await user.click(screen.getByRole('checkbox', { name: /Acepto los términos/ }))
    await user.click(screen.getByRole('button', { name: 'Firmar y terminar' }))

    expect(await screen.findByRole('heading', { name: 'Deja tu cuenta al día' })).toBeInTheDocument()
    expect(posts.map((post) => post.url)).toEqual(['checkin/', 'complete/'])
    expect(posts[0]!.body).toEqual({ step: 'signature', signature: 'data:image/png;base64,U0lHTkVE', accept_terms: true, marketing_consent: false })

    await user.click(screen.getByRole('button', { name: 'Pagar en el hotel' }))
    expect(await screen.findByRole('heading', { name: 'Check-in listo' })).toBeInTheDocument()
  })

  it('takes the guest to the gateway to pay the balance', async () => {
    const posts = serve(registeredCheckin({ status: 'completed', current_step: 'payment', missing: [] }))
    const { user } = renderPage()

    await user.click(await screen.findByRole('button', { name: 'Pagar $ 761.600' }))

    await vi.waitFor(() => expect(goTo).toHaveBeenCalledWith('http://localhost:5173/sim/pay/HT-7K2M9Q-AB12CD'))
    expect(posts.map((post) => post.url)).toEqual(['pay/'])
  })
})

describe('CheckinPage — closed', () => {
  it('says when the online check-in opens', async () => {
    serve(makeCheckin({ window: { opens_on: '2026-10-13', is_open: false, reason: 'not_open_yet' } }))
    renderPage()

    expect(await screen.findByText(/El check-in online abre el 13 de octubre/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Guardar y continuar' })).not.toBeInTheDocument()
  })

  it('explains that the link is not valid', async () => {
    server.use(http.get(`${BASE}checkin/`, () => HttpResponse.json({ detail: 'x', code: 'invalid_link' }, { status: 404 })))
    renderPage()

    expect(await screen.findByRole('heading', { name: 'Este enlace no es válido' })).toBeInTheDocument()
  })
})
