import { describe, expect, it } from 'vitest'
import { ApiError } from '@/lib/api'
import { errorMessage } from '@/lib/errors'
import i18n from '@/lib/i18n'

const t = i18n.getFixedT('es')

describe('errorMessage', () => {
  it("uses the backend's Spanish detail when there is one", () => {
    expect(errorMessage(new ApiError(409, 'no_availability', 'No hay disponibilidad en esas fechas'), t)).toBe(
      'No hay disponibilidad en esas fechas',
    )
  })

  it('explains network failures', () => {
    expect(errorMessage(new ApiError(0, 'network_error', 'Failed to fetch'), t)).toBe(
      'Sin conexión con el servidor. Revisa tu red e inténtalo de nuevo.',
    )
  })

  it('falls back to a generic sentence for errors without a readable detail', () => {
    expect(errorMessage(new ApiError(502, 'http_error', 'HTTP 502'), t)).toBe('Algo salió mal. Inténtalo de nuevo.')
    expect(errorMessage(new Error('boom'), t)).toBe('Algo salió mal. Inténtalo de nuevo.')
    expect(errorMessage(undefined, t)).toBe('Algo salió mal. Inténtalo de nuevo.')
  })

  it('names suspended organizations and missing permissions even without detail', () => {
    expect(errorMessage(new ApiError(402, 'organization_suspended', 'HTTP 402'), t)).toBe(
      'Tu organización está suspendida por falta de pago.',
    )
    expect(errorMessage(new ApiError(403, 'permission_denied', 'HTTP 403'), t)).toBe('No tienes permiso para esta acción.')
  })
})
