import { screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ProfileDialog } from '@/app/shell/ProfileDialog'
import { makeMe, mockMe } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'

beforeEach(() => {
  document.cookie = 'csrftoken=t; path=/'
})

describe('ProfileDialog', () => {
  it('shows the saved phone and keeps it when another field is saved', async () => {
    mockMe(makeMe({ full_name: 'Valentina Ríos', phone: '+573001112233' }))
    let saved: unknown
    server.use(
      http.patch('/api/v1/accounts/me/', async ({ request }) => {
        saved = await request.json()
        return HttpResponse.json(makeMe({ full_name: 'Valentina Rojas', phone: '+573001112233' }))
      }),
    )
    const onOpenChange = vi.fn()
    const { user } = renderWithProviders(<ProfileDialog open onOpenChange={onOpenChange} />)

    const phone = await screen.findByLabelText('Teléfono')
    await waitFor(() => expect(phone).toHaveValue('+573001112233'))

    const name = screen.getByLabelText('Nombre completo')
    await user.clear(name)
    await user.type(name, 'Valentina Rojas')
    await user.click(screen.getByRole('button', { name: 'Guardar cambios' }))

    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false))
    expect(saved).toEqual({ full_name: 'Valentina Rojas', phone: '+573001112233', language: 'es' })
  })

  it('names every form control, including the native select behind the language picker', async () => {
    mockMe(makeMe())
    renderWithProviders(<ProfileDialog open onOpenChange={vi.fn()} />)

    const form = (await screen.findByLabelText('Teléfono')).closest('form')
    const controls = [...(form?.querySelectorAll('input, select, textarea') ?? [])]
    expect(controls.length).toBeGreaterThan(2)
    // Browsers flag unnamed controls (autofill cannot map them).
    expect(controls.filter((control) => !control.id && !control.getAttribute('name'))).toEqual([])
  })
})
