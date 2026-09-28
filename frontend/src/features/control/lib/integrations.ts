import type { Integration, IntegrationKind } from '../api'

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
