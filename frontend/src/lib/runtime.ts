import { useQuery } from '@tanstack/react-query'
import { publicApi } from './api'

/**
 * What the backend says about this installation (`GET /api/v1/public/core/config/`, plan P1):
 * development or production, whether simulators and simulated providers exist, the public URL
 * (webhooks, links sent to guests) and the support channels.
 */
export interface SupportContact {
  /** Phone in international format (`+57 300 123 4567`); empty = not offered. */
  whatsapp: string
  email: string
  docs_url: string
}

export interface RuntimeConfig {
  environment: 'development' | 'production'
  simulations_enabled: boolean
  public_base_url: string
  support: SupportContact
}

export const RUNTIME_CONFIG_QUERY_KEY = ['runtime-config'] as const

/**
 * Used until the answer arrives (and if it fails): the cautious production values, so simulators never
 * flash in the menu of a real hotel. In development they appear as soon as the config loads.
 */
export const FALLBACK_RUNTIME_CONFIG: RuntimeConfig = {
  environment: 'production',
  simulations_enabled: false,
  public_base_url: typeof window === 'undefined' ? '' : window.location.origin,
  support: { whatsapp: '', email: '', docs_url: '' },
}

export function fetchRuntimeConfig(): Promise<RuntimeConfig> {
  return publicApi.get<RuntimeConfig>('/core/config/')
}

/** The runtime config (loaded once per page load; the fallback while loading or on error). */
export function useRuntimeConfig(): RuntimeConfig & { loaded: boolean } {
  const { data } = useQuery({
    queryKey: RUNTIME_CONFIG_QUERY_KEY,
    queryFn: fetchRuntimeConfig,
    staleTime: Infinity,
    gcTime: Infinity,
  })
  return data ? { ...data, loaded: true } : { ...FALLBACK_RUNTIME_CONFIG, loaded: false }
}

/** True when this is a demo/development install whose integrations are simulated (the shell shows a banner). */
export function isDemoEnvironment(config: RuntimeConfig): boolean {
  return config.simulations_enabled && config.environment !== 'production'
}

/** `https://wa.me/573001234567?text=…` for a phone in any format; null without digits. */
export function whatsappLink(phone: string, text?: string): string | null {
  const digits = phone.replace(/\D/g, '')
  if (!digits) return null
  return `https://wa.me/${digits}${text ? `?text=${encodeURIComponent(text)}` : ''}`
}

/** `mailto:` link with an optional subject and body. */
export function mailtoLink(email: string, subject?: string, body?: string): string | null {
  if (!email) return null
  const params = new URLSearchParams()
  if (subject) params.set('subject', subject)
  if (body) params.set('body', body)
  // URLSearchParams encodes spaces as "+", which mail clients show literally.
  const query = params.toString().replace(/\+/g, '%20')
  return `mailto:${email}${query ? `?${query}` : ''}`
}

/** A support channel is offered when the backend gives a value for it. */
export function hasSupportChannel(support: SupportContact): boolean {
  return Boolean(support.whatsapp || support.email || support.docs_url)
}
