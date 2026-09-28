import type { Integration, IntegrationKind, IntegrationMode } from '../api'

/**
 * Facts about each integration kind that the backend does not describe: the public webhook the provider calls
 * (the hotel pastes it in the provider's panel) and the page of Housetel where the rest of its setup lives.
 */
interface KindMeta {
  /** Public webhook path (real mode), shown with the current origin. */
  webhookPath?: string
  /** Related settings page + i18n key (`integrations.related.<key>`). */
  related?: { path: string; key: string; permission: string }
}

export const KIND_META: Record<IntegrationKind, KindMeta> = {
  payments: { webhookPath: '/api/v1/public/finance/webhooks/wompi/' },
  channel_ical: { related: { path: '/app/channels', key: 'channels', permission: 'distribution.view' } },
  channel_channex: { related: { path: '/app/channels', key: 'channels', permission: 'distribution.view' } },
  einvoice: { related: { path: '/app/settings/compliance', key: 'compliance', permission: 'compliance.settings' } },
  sire: { related: { path: '/app/compliance?tab=sire', key: 'complianceBoard', permission: 'compliance.view' } },
  tra: { related: { path: '/app/settings/compliance', key: 'compliance', permission: 'compliance.settings' } },
  email: { related: { path: '/app/settings/messaging', key: 'messaging', permission: 'messaging.templates' } },
  whatsapp: {
    webhookPath: '/api/v1/public/messaging/webhooks/whatsapp/',
    related: { path: '/app/settings/messaging', key: 'messaging', permission: 'messaging.templates' },
  },
  llm: { related: { path: '/app/settings/ai', key: 'ai', permission: 'ai.settings' } },
}

/** Display order: money first, then channels, legal, messaging and AI (the backend order is by kind). */
export const KIND_ORDER: IntegrationKind[] = [
  'payments',
  'channel_channex',
  'channel_ical',
  'einvoice',
  'tra',
  'sire',
  'whatsapp',
  'email',
  'llm',
]

export function sortIntegrations(items: Integration[]): Integration[] {
  const rank = (kind: IntegrationKind) => {
    const index = KIND_ORDER.indexOf(kind)
    return index === -1 ? KIND_ORDER.length : index
  }
  return [...items].sort((a, b) => rank(a.kind) - rank(b.kind))
}

/** Real mode but required credentials are still missing (the provider can't work yet). */
export function needsCredentials(integration: Integration): boolean {
  return integration.mode === 'real' && integration.missing_required.length > 0
}

/** Kinds whose simulated mode stays available where simulations are off (`core.integrations.SIMULATION_EXEMPT_KINDS`). */
const SIMULATION_EXEMPT: readonly IntegrationKind[] = ['email', 'llm']

/**
 * Modes the hotel may pick here. The backend already sends only the allowed ones in `available_modes`
 * (`core.integrations.available_modes`, P-INT); the filter stays as a guard for an older backend: minus
 * "simulated" where this installation has simulations off (production) — except email and AI, whose simulated
 * mode is a legitimate fallback. `providers` keeps every registered provider (the "not here" vs "no provider"
 * hint of a disabled mode).
 */
export function allowedModes(integration: Integration, simulationsEnabled: boolean): IntegrationMode[] {
  return integration.available_modes.filter(
    (mode) => mode !== 'simulated' || simulationsEnabled || SIMULATION_EXEMPT.includes(integration.kind),
  )
}

/** Working for real: real mode, on and nothing required missing (what `core.integrations.is_live` checks). */
export function isLive(integration: Integration): boolean {
  return integration.mode === 'real' && integration.enabled && integration.missing_required.length === 0
}
