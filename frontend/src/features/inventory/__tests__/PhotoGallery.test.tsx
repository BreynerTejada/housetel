import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError } from '@/lib/api'
import { useSession } from '@/lib/session'
import { auroraProperty } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import type { Photo } from '../api'
import { PhotoGallery } from '../components/PhotoGallery'

const PATH = '/inventory/room-types/rt-dbl/photos/'

function png(name: string) {
  return new File([new Uint8Array([137, 80, 78, 71])], name, { type: 'image/png' })
}

function photo(n: number): Photo {
  return { id: `p${n}`, url: `/media/photos/${n}.png`, caption: {}, sort_order: n, room_type: 'rt-dbl', created_at: '' }
}

beforeEach(() => {
  document.cookie = 'csrftoken=t; path=/'
  useSession.setState({ propertyId: auroraProperty.id, loggedOut: false })
  server.use(http.get(`/api/v1${PATH}`, () => HttpResponse.json([])))
})

afterEach(() => {
  vi.restoreAllMocks() // (toasts are dismissed after every test by src/test/setup.ts)
})

// jsdom's File cannot go through Node's fetch, so uploads are checked where they leave the component: the
// multipart body handed to the API client (multipart transport is covered by src/lib/__tests__/api.test.ts).
describe('PhotoGallery uploads', () => {
  it('sends each image as multipart and counts only the ones that were really uploaded', async () => {
    const sent: { path: string; name: string }[] = []
    vi.spyOn(api, 'post').mockImplementation(async (path, _body, opts) => {
      const file = opts?.formData?.get('image') as File
      sent.push({ path, name: file.name })
      if (file.name === 'b.png') throw new ApiError(400, 'validation_error', 'Formatos permitidos: JPG, PNG o WEBP')
      return photo(sent.length) as never
    })
    const { user } = renderWithProviders(<PhotoGallery roomTypeId="rt-dbl" canEdit label="Fotos de la categoría" />)

    await user.upload(await screen.findByLabelText(/Arrastra fotos aquí/), [png('a.png'), png('b.png'), png('c.png')])

    expect(await screen.findByText('Se subieron 2 fotos')).toBeInTheDocument()
    expect(screen.getByText('No se pudo subir b.png: Formatos permitidos: JPG, PNG o WEBP')).toBeInTheDocument()
    expect(sent).toEqual([
      { path: PATH, name: 'a.png' },
      { path: PATH, name: 'b.png' },
      { path: PATH, name: 'c.png' },
    ])
  })

  it('does not announce a success when every upload fails', async () => {
    vi.spyOn(api, 'post').mockRejectedValue(new ApiError(400, 'validation_error', 'La imagen supera 10 MB'))
    const { user } = renderWithProviders(<PhotoGallery roomTypeId="rt-dbl" canEdit label="Fotos de la categoría" />)

    await user.upload(await screen.findByLabelText(/Arrastra fotos aquí/), [png('grande.png')])

    expect(await screen.findByText('No se pudo subir grande.png: La imagen supera 10 MB')).toBeInTheDocument()
    expect(screen.queryByText(/Se subi/)).not.toBeInTheDocument()
  })
})
