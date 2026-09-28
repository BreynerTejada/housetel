import type {
  Conversation,
  ConversationDetail,
  EffectiveTemplate,
  LifecycleRule,
  Message,
  Page,
  Variable,
} from '../api'

export const CONVERSATION_ID = '0b9a4f5e-0000-4000-8000-00000000c001'
export const RESERVATION_ID = '0b9a4f5e-0000-4000-8000-00000000r001'
export const GUEST_ID = '0b9a4f5e-0000-4000-8000-00000000g001'

export function page<T>(results: T[]): Page<T> {
  return { count: results.length, next: null, previous: null, results }
}

export function makeConversation(overrides: Partial<Conversation> = {}): Conversation {
  return {
    id: CONVERSATION_ID,
    channel: 'whatsapp',
    status: 'open',
    contact_name: 'Laura Gómez',
    address: '+573001112233',
    display_name: 'Laura Gómez',
    guest: {
      id: GUEST_ID,
      full_name: 'Laura Gómez',
      email: 'laura@example.com',
      phone: '+573001112233',
      language: 'es',
      is_vip: true,
    },
    reservation: {
      id: RESERVATION_ID,
      code: 'HT-LAURA1',
      status: 'checked_in',
      checkin_date: '2026-09-24',
      checkout_date: '2026-09-27',
      room: '301',
    },
    assigned_to: null,
    last_message_at: '2026-09-25T15:20:00Z',
    last_message_preview: '¿Tienen toallas para la playa?',
    last_message_direction: 'in',
    last_inbound_at: '2026-09-25T15:20:00Z',
    unread_count: 2,
    whatsapp_window_open: true,
    created_at: '2026-09-20T12:00:00Z',
    ...overrides,
  }
}

export function makeDetail(overrides: Partial<ConversationDetail> = {}): ConversationDetail {
  return {
    ...makeConversation(),
    context: {
      guest: {
        id: GUEST_ID,
        full_name: 'Laura Gómez',
        first_name: 'Laura',
        email: 'laura@example.com',
        phone: '+573001112233',
        language: 'es',
        is_vip: true,
        nationality: 'CO',
        country_of_residence: 'CO',
      },
      reservation: {
        id: RESERVATION_ID,
        code: 'HT-LAURA1',
        status: 'checked_in',
        source: 'phone',
        checkin_date: '2026-09-24',
        checkout_date: '2026-09-27',
        nights: 3,
        adults: 2,
        children: 0,
        currency: 'COP',
        total_amount: '1142400.00',
        balance: '380800.00',
        room_types: ['Suite Vista al Mar'],
        rooms: ['301'],
      },
    },
    ...overrides,
  }
}

export function makeMessage(overrides: Partial<Message> = {}): Message {
  return {
    id: 'm-1',
    direction: 'in',
    channel: 'whatsapp',
    sender_label: 'Laura Gómez',
    recipient: '',
    subject: '',
    body: '¿Tienen toallas para la playa?',
    status: 'received',
    error: '',
    template_code: '',
    ai_generated: false,
    sent_by: null,
    created_at: '2026-09-25T15:20:00Z',
    status_updated_at: null,
    ...overrides,
  }
}

function template(code: string, channel: 'email' | 'whatsapp', language: 'es' | 'en', label: [string, string], overrides: Partial<EffectiveTemplate> = {}): EffectiveTemplate {
  return {
    key: `${code}:${channel}:${language}`,
    code,
    label: { es: label[0], en: label[1] },
    is_system_code: true,
    channel,
    language,
    source: 'system',
    id: null,
    subject: channel === 'email' ? 'Reserva confirmada · {{reservation.code}}' : '',
    body: 'Hola {{guest.first_name}}, tu reserva {{reservation.code}} está confirmada.',
    is_active: true,
    wa_template_name: '',
    wa_template_params: [],
    updated_at: null,
    organization_template_id: null,
    property_template_id: null,
    ...overrides,
  }
}

export function makeTemplates(): EffectiveTemplate[] {
  const labels: Record<string, [string, string]> = {
    confirmation: ['Confirmación de reserva', 'Booking confirmation'],
    payment_link: ['Link de pago', 'Payment link'],
  }
  const rows: EffectiveTemplate[] = []
  for (const code of Object.keys(labels)) {
    for (const channel of ['email', 'whatsapp'] as const) {
      for (const language of ['es', 'en'] as const) rows.push(template(code, channel, language, labels[code]!))
    }
  }
  rows.push(
    template('welcome_drink', 'whatsapp', 'es', ['Cóctel de bienvenida', 'Cóctel de bienvenida'], {
      is_system_code: false,
      source: 'organization',
      id: 't-org-1',
      organization_template_id: 't-org-1',
      body: '¡Hola {{guest.first_name}}! Te esperamos con un cóctel 🍹',
    }),
  )
  return rows
}

export const VARIABLES: Variable[] = [
  { key: 'guest.first_name', group: 'guest', label: { es: 'Nombre del huésped', en: 'Guest first name' }, example: { es: 'Ana', en: 'Ana' } },
  { key: 'reservation.code', group: 'reservation', label: { es: 'Código de la reserva', en: 'Booking code' }, example: { es: 'HT-7K2M9Q', en: 'HT-7K2M9Q' } },
  { key: 'portal_url', group: 'links', label: { es: 'Portal del huésped', en: 'Guest portal link' }, example: { es: 'https://…/g/…', en: 'https://…/g/…' } },
]

export function makeRules(): LifecycleRule[] {
  const base = { enabled: true, template_code: '', send_after: '09:00' }
  return [
    { ...base, id: 'r1', event: 'confirmation', label: { es: 'Confirmación de reserva', en: 'Booking confirmation' }, days_offset: 0, uses_offset: false, channels: ['email', 'whatsapp'], template_code: 'confirmation', scheduled: false },
    { ...base, id: 'r2', event: 'pre_arrival', label: { es: 'Antes de la llegada (check-in en línea)', en: 'Before arrival (online check-in)' }, days_offset: 3, uses_offset: true, channels: ['email', 'whatsapp'], template_code: 'pre_arrival', scheduled: true },
    { ...base, id: 'r3', event: 'arrival_day', label: { es: 'Día de llegada', en: 'Arrival day' }, days_offset: 0, uses_offset: false, channels: ['whatsapp'], template_code: 'arrival_day', scheduled: true },
    { ...base, id: 'r4', event: 'post_stay', label: { es: 'Después de la estadía', en: 'After the stay' }, days_offset: 1, uses_offset: true, channels: ['email'], template_code: 'post_stay', scheduled: true },
    { ...base, id: 'r5', event: 'payment_reminder', label: { es: 'Recordatorio de pago', en: 'Payment reminder' }, days_offset: 3, uses_offset: true, channels: ['email', 'whatsapp'], template_code: 'payment_reminder', scheduled: true },
    { ...base, id: 'r6', event: 'cancellation', label: { es: 'Cancelación', en: 'Cancellation' }, days_offset: 0, uses_offset: false, channels: ['email'], template_code: 'cancellation', scheduled: false },
  ]
}
