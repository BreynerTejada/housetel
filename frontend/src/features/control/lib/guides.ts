import type { Lang } from '@/lib/format'
import type { IntegrationKind } from '../api'

/**
 * Step-by-step guides to switch each integration to real mode (plan P6): the account to create (official
 * link), the order of the steps, where each key lives in the provider's panel, sandbox vs production and where
 * to paste the webhook. They mirror the long guide in `docs/integraciones-reales.md` (section `docsSection`).
 * The texts live here and not in the locale files so they load with the Integrations page only.
 */

export interface GuideStep {
  title: string
  body: string
  /** Optional official link for this step. */
  link?: { label: string; href: string }
  /** Where the webhook URL box belongs (shown right after this step). */
  webhook?: boolean
}

export interface GuideKey {
  /** `CONFIG_FIELDS` name (the label comes from the backend so both always match). */
  field: string
  where: string
}

export interface IntegrationGuide {
  /** Who provides the real service (Wompi, Factus, Meta…). */
  provider: string
  /** The account to create and its official page (null: nothing new to create). */
  account: { label: string; href: string } | null
  steps: GuideStep[]
  keys: GuideKey[]
  /** Test vs live environment of the provider (null when it has none). */
  environments: { sandboxLabel: string; sandbox: string; productionLabel: string; production: string } | null
  /** One-line caveat (no sandbox, manual upload…). */
  note?: string
  /** Heading of this provider in docs/integraciones-reales.md. */
  docsSection: string
}

type Guides = Record<IntegrationKind, IntegrationGuide>

const ES: Guides = {
  payments: {
    provider: 'Wompi',
    account: { label: 'Crear cuenta de comercio en Wompi', href: 'https://comercios.wompi.co/' },
    environments: {
      sandboxLabel: 'Sandbox (pruebas)',
      sandbox: 'Llaves pub_test_ y prv_test_: los pagos no mueven dinero. Aprueba con la tarjeta 4242 4242 4242 4242.',
      productionLabel: 'Producción',
      production: 'Llaves pub_prod_ y prv_prod_: cobros reales a la cuenta bancaria del hotel. Wompi debe haber validado tu cuenta.',
    },
    steps: [
      {
        title: 'Crea la cuenta de tu hotel en Wompi',
        body: 'Regístrate en el panel de comercios con el NIT o la cédula del titular. Mientras Wompi valida tus documentos puedes trabajar con el ambiente de pruebas.',
        link: { label: 'comercios.wompi.co', href: 'https://comercios.wompi.co/' },
      },
      {
        title: 'Copia las llaves y los secretos',
        body: 'En Desarrolladores › Llaves del API están la llave pública y la privada; en Desarrolladores › Secretos para integración técnica, los de eventos e integridad. Pégalos abajo.',
      },
      {
        title: 'Pega la URL de eventos en Wompi',
        body: 'En Desarrolladores › Seguimiento de transacciones › URL de eventos: así Wompi avisa a Housetel cuando un pago se aprueba, se rechaza o se anula.',
        webhook: true,
      },
      {
        title: 'Prueba en Sandbox',
        body: 'Guarda con el ambiente Sandbox, pulsa «Probar conexión» y haz una reserva de prueba en tu motor de reservas pagando con la tarjeta 4242 4242 4242 4242.',
      },
      {
        title: 'Pasa a producción',
        body: 'Cuando Wompi apruebe tu cuenta, cambia el ambiente a Producción y reemplaza las cuatro llaves por las de producción.',
      },
    ],
    keys: [
      { field: 'public_key', where: 'Desarrolladores › Llaves del API (empieza por pub_test_ o pub_prod_)' },
      { field: 'private_key', where: 'Desarrolladores › Llaves del API (empieza por prv_test_ o prv_prod_)' },
      { field: 'integrity_secret', where: 'Desarrolladores › Secretos para integración técnica › Integridad' },
      { field: 'events_secret', where: 'Desarrolladores › Secretos para integración técnica › Eventos' },
    ],
    docsSection: '1. Pagos en línea: Wompi',
  },
  channel_channex: {
    provider: 'Channex',
    account: { label: 'Crear cuenta en el staging de Channex', href: 'https://staging.channex.io/' },
    environments: {
      sandboxLabel: 'Staging',
      sandbox: 'staging.channex.io: propiedades, OTAs y reservas de prueba, sin afectar ventas reales.',
      productionLabel: 'Producción',
      production: 'app.channex.io: tus canales reales (Booking.com, Expedia…). Requiere tu cuenta comercial con Channex.',
    },
    steps: [
      {
        title: 'Crea una cuenta en el staging de Channex',
        body: 'Es el ambiente de pruebas gratuito para conectar un PMS sin tocar reservas reales.',
        link: { label: 'staging.channex.io', href: 'https://staging.channex.io/' },
      },
      {
        title: 'Crea tu propiedad y copia su ID',
        body: 'En Propiedades crea el hotel con sus categorías y planes de tarifa. El ID (un UUID) está en el detalle de la propiedad.',
      },
      {
        title: 'Genera una API key',
        body: 'En Perfil › API keys crea una llave para Housetel y pégala abajo junto con el ID de la propiedad.',
      },
      {
        title: 'Relaciona categorías y tarifas en Canales',
        body: 'Guarda aquí y abre Canales › Conectar › Channex: une cada categoría y plan de Housetel con los de Channex. Housetel envía disponibilidad y tarifas, y descarga las reservas cada 5 minutos.',
      },
      {
        title: 'Conecta tus OTAs dentro de Channex',
        body: 'Booking.com, Expedia y los demás canales se conectan en Channex. Para producción cambia el ambiente y la API key a los de app.channex.io.',
      },
    ],
    note: 'Channex exige certificar la integración de cada PMS antes de abrir producción: para un piloto usa iCal o el channel manager que el hotel ya tenga.',
    keys: [
      { field: 'property_id', where: 'Channex › Propiedades › tu hotel (ID de la propiedad)' },
      { field: 'api_key', where: 'Channex › Perfil › API keys' },
    ],
    docsSection: '4. Canales: Channex (staging)',
  },
  channel_ical: {
    provider: 'iCal',
    account: null,
    environments: null,
    note: 'No necesitas una cuenta nueva: usas los calendarios que ya te dan Airbnb, VRBO o Booking.com.',
    steps: [
      {
        title: 'Activa el modo real',
        body: 'En modo real Housetel descarga por HTTPS los calendarios de tus portales cada 15 minutos (en simulado solo lee los de Housetel).',
      },
      {
        title: 'Copia el enlace de exportación del portal',
        body: 'En Airbnb, VRBO o Booking.com busca la opción de sincronizar o exportar el calendario (.ics) de cada anuncio y copia el enlace.',
      },
      {
        title: 'Pégalo en Canales',
        body: 'En Canales › Conectar › iCal pega el enlace en la categoría o habitación que corresponde. Cada reserva del portal bloquea esas fechas en Housetel.',
      },
      {
        title: 'Lleva el calendario de Housetel al portal',
        body: 'Copia la URL de exportación de esa conexión en Canales y pégala como calendario importado en el portal, para que no te vendan fechas ya ocupadas.',
      },
    ],
    keys: [],
    docsSection: '5. Calendarios iCal',
  },
  einvoice: {
    provider: 'Factus',
    account: { label: 'Conocer Factus (proveedor tecnológico)', href: 'https://www.factus.com.co/' },
    environments: {
      sandboxLabel: 'Sandbox',
      sandbox: 'Facturas de prueba sin validez fiscal, para probar la integración y el set de pruebas de la DIAN.',
      productionLabel: 'Producción',
      production: 'Facturas válidas ante la DIAN con tu resolución de numeración. Requiere la habilitación terminada.',
    },
    steps: [
      {
        title: 'Habilítate como facturador electrónico',
        body: 'En el servicio «Facturando electrónicamente» de la DIAN registra a tu empresa y elige a Factus como proveedor tecnológico.',
        link: { label: 'dian.gov.co', href: 'https://www.dian.gov.co/' },
      },
      {
        title: 'Solicita la resolución de numeración',
        body: 'Pide en la DIAN la resolución de facturación electrónica (prefijo y rango) y regístrala en Ajustes legales de Housetel.',
      },
      {
        title: 'Pide tus credenciales de API a Factus',
        body: 'Factus entrega client ID, client secret, usuario y contraseña, primero para su sandbox y al final de la habilitación para producción.',
      },
      {
        title: 'Prueba en Sandbox',
        body: 'Guarda con el ambiente Sandbox, pulsa «Probar conexión» y emite una factura desde la pestaña Legal de una reserva en casa.',
      },
      {
        title: 'Pasa a producción',
        body: 'Con la habilitación aprobada cambia el ambiente a Producción, actualiza las credenciales y, si Factus te los dio, los ID de rango.',
      },
    ],
    keys: [
      { field: 'client_id', where: 'Credenciales de API que entrega Factus' },
      { field: 'client_secret', where: 'Credenciales de API que entrega Factus' },
      { field: 'username', where: 'El correo con el que entras a Factus' },
      { field: 'password', where: 'La contraseña de tu usuario de Factus' },
      { field: 'numbering_range_id', where: 'Factus › rangos de numeración (vacío: el de la resolución activa)' },
    ],
    docsSection: '2. Factura electrónica DIAN: Factus',
  },
  tra: {
    provider: 'MinCIT (TRA)',
    account: { label: 'Solicitar el token PMS de MinCIT', href: 'https://pms.mincit.gov.co/token/' },
    environments: null,
    note: 'MinCIT no tiene ambiente de pruebas: en modo real cada check-in registra la TRA de verdad.',
    steps: [
      {
        title: 'Ten a mano tu RNT vigente',
        body: 'El token se pide con el Registro Nacional de Turismo del establecimiento. Escríbelo también en el perfil del hotel.',
      },
      {
        title: 'Solicita el token PMS',
        body: 'En pms.mincit.gov.co/token pide el token de integración para tu RNT.',
        link: { label: 'pms.mincit.gov.co/token', href: 'https://pms.mincit.gov.co/token/' },
      },
      {
        title: 'Pégalo aquí y prueba la conexión',
        body: 'Guárdalo en «Token PMS del RNT» y pulsa «Probar conexión».',
      },
      {
        title: 'Revisa los registros',
        body: 'Cada check-in envía la TRA del titular y sus acompañantes. En Legal › TRA ves el estado de cada huésped y puedes reintentar.',
      },
    ],
    keys: [
      { field: 'token', where: 'pms.mincit.gov.co/token, con el RNT del establecimiento' },
      { field: 'establishment_id', where: 'Tu número de RNT (vacío: el del perfil del hotel)' },
    ],
    docsSection: '6. TRA (Tarjeta de Registro Hotelero, MinCIT)',
  },
  sire: {
    provider: 'Migración Colombia (SIRE)',
    account: { label: 'Portal SIRE de Migración Colombia', href: 'https://apps.migracioncolombia.gov.co/sire/' },
    environments: null,
    note: 'El SIRE no tiene API para hoteles: Housetel genera el archivo y tú lo cargas en el portal.',
    steps: [
      {
        title: 'Registra el establecimiento en el SIRE',
        body: 'Migración Colombia te asigna un usuario del SIRE y el código del establecimiento.',
      },
      {
        title: 'Completa los códigos en Ajustes legales',
        body: 'El código del establecimiento y el de la ciudad van en cada línea del archivo.',
      },
      {
        title: 'Genera el archivo',
        body: 'La automatización diaria (08:00) arma el archivo con las entradas y salidas de extranjeros de ayer; también lo puedes generar en Legal › SIRE.',
      },
      {
        title: 'Cárgalo y márcalo como reportado',
        body: 'Súbelo en el cargue masivo del SIRE y marca el reporte en Housetel con el número de acuse.',
      },
    ],
    keys: [],
    docsSection: '7. SIRE (Migración Colombia)',
  },
  whatsapp: {
    provider: 'Meta (WhatsApp Cloud API)',
    account: { label: 'Abrir Meta for Developers', href: 'https://developers.facebook.com/apps/' },
    environments: {
      sandboxLabel: 'Número de prueba',
      sandbox: 'Meta te da un número de prueba que solo escribe a los números que verifiques (máximo 5).',
      productionLabel: 'Tu número',
      production: 'El número del hotel, verificado en Meta, con los límites de mensajes de tu nivel.',
    },
    steps: [
      {
        title: 'Prepara tu portafolio de Meta Business',
        body: 'Verifica tu negocio en Meta Business Suite: lo necesitas para usar el número del hotel.',
        link: { label: 'business.facebook.com', href: 'https://business.facebook.com/' },
      },
      {
        title: 'Crea una app de tipo Negocio con WhatsApp',
        body: 'En Meta for Developers › Mis apps crea la app y agrega el producto WhatsApp.',
      },
      {
        title: 'Registra el número y copia su ID',
        body: 'En WhatsApp › Configuración de la API agrega el número del hotel (no puede seguir activo en la app de WhatsApp) y copia su Phone number ID.',
      },
      {
        title: 'Crea un token permanente',
        body: 'En la configuración del negocio › Usuarios del sistema crea un usuario, asígnale la app y genera un token con whatsapp_business_messaging y whatsapp_business_management.',
      },
      {
        title: 'Guarda aquí y suscribe el webhook',
        body: 'Primero guarda en Housetel el Phone number ID, el token y un token de verificación que inventes (Meta lo comprueba contra el hotel ya en modo real). Después, en WhatsApp › Configuración › Webhook pega la URL de abajo con ese mismo token y suscríbete al campo messages.',
        webhook: true,
      },
      {
        title: 'Aprueba tus plantillas',
        body: 'Fuera de las 24 horas desde el último mensaje del huésped solo se envían plantillas aprobadas por Meta, en español y en inglés.',
      },
    ],
    keys: [
      { field: 'phone_number_id', where: 'WhatsApp › Configuración de la API' },
      { field: 'access_token', where: 'Configuración del negocio › Usuarios del sistema › Generar token' },
      { field: 'app_secret', where: 'Tu app › Configuración › Básica › Clave secreta de la app' },
      { field: 'verify_token', where: 'Lo inventas tú: el mismo texto aquí y en el webhook de Meta' },
    ],
    docsSection: '3. WhatsApp: WhatsApp Cloud API (Meta)',
  },
  email: {
    provider: 'SMTP',
    account: null,
    environments: null,
    note: 'Sin configurar nada, los correos salen del servidor de Housetel con el nombre de tu hotel.',
    steps: [
      {
        title: 'Decide el remitente',
        body: 'Para enviar desde tu dominio (reservas@tuhotel.com) crea una cuenta SMTP en un proveedor de correo transaccional (Amazon SES, Postmark, Brevo…).',
      },
      {
        title: 'Configura SPF, DKIM y DMARC',
        body: 'Agrega en el DNS de tu dominio los registros que te da el proveedor. Sin ellos los correos llegan a spam o se rechazan.',
      },
      {
        title: 'Escribe los datos del servidor',
        body: 'Servidor, puerto (587 con TLS), usuario y contraseña del proveedor, y el remitente con una dirección de tu dominio.',
      },
      {
        title: 'Prueba la conexión',
        body: 'Pulsa «Probar conexión» y envía una confirmación de reserva de prueba a tu correo.',
      },
    ],
    keys: [
      { field: 'smtp_host', where: 'Panel del proveedor › credenciales SMTP' },
      { field: 'smtp_username', where: 'Panel del proveedor › credenciales SMTP' },
      { field: 'smtp_password', where: 'Panel del proveedor › credenciales SMTP' },
      { field: 'from_email', where: 'Una dirección de tu dominio ya verificado en el proveedor' },
    ],
    docsSection: '8. Correo transaccional (SMTP con SPF y DKIM)',
  },
  llm: {
    provider: 'Gemini / Claude',
    account: { label: 'Crear una clave en Google AI Studio', href: 'https://aistudio.google.com/apikey' },
    environments: {
      sandboxLabel: 'Nivel gratuito',
      sandbox: 'La clave de la plataforma o una tuya sin facturación: pocas solicitudes al día; al agotarse, el asistente sigue en modo simulado.',
      productionLabel: 'Con facturación',
      production: 'Tu clave de Gemini con facturación en Google Cloud, o una de Claude: más cuota y sin cortes.',
    },
    steps: [
      {
        title: 'Empieza con la clave de la plataforma',
        body: 'Por defecto la IA usa la clave de Housetel, con cuota compartida entre hoteles.',
      },
      {
        title: 'Usa tu propia clave de Gemini',
        body: 'Crea una clave en Google AI Studio y, para más cuota, activa la facturación de su proyecto en Google Cloud.',
        link: { label: 'aistudio.google.com', href: 'https://aistudio.google.com/apikey' },
      },
      {
        title: 'O conecta Claude',
        body: 'Crea una clave en la consola de Anthropic, elige Claude como proveedor y pégala abajo.',
        link: { label: 'console.anthropic.com', href: 'https://console.anthropic.com/' },
      },
      {
        title: 'Prueba',
        body: 'Pulsa «Probar conexión» y hazle una pregunta al copiloto.',
      },
    ],
    keys: [{ field: 'api_key', where: 'Google AI Studio › Get API key, o la consola de Anthropic › API keys' }],
    docsSection: '9. IA de pago: Gemini y Claude',
  },
}

const EN: Guides = {
  payments: {
    provider: 'Wompi',
    account: { label: 'Create a Wompi merchant account', href: 'https://comercios.wompi.co/' },
    environments: {
      sandboxLabel: 'Sandbox (testing)',
      sandbox: 'pub_test_ and prv_test_ keys: payments move no money. Approve with the card 4242 4242 4242 4242.',
      productionLabel: 'Production',
      production: 'pub_prod_ and prv_prod_ keys: real charges to the hotel\'s bank account. Wompi must have approved your account.',
    },
    steps: [
      {
        title: 'Create your hotel\'s Wompi account',
        body: 'Sign up on the merchant panel with the company tax ID (NIT) or the owner\'s ID. While Wompi reviews your documents you can work in the test environment.',
        link: { label: 'comercios.wompi.co', href: 'https://comercios.wompi.co/' },
      },
      {
        title: 'Copy the keys and secrets',
        body: 'Developers › API keys has the public and private keys; Developers › Secrets for technical integration has the events and integrity secrets. Paste them below.',
      },
      {
        title: 'Paste the events URL in Wompi',
        body: 'In Developers › Transaction tracking › Events URL: that is how Wompi tells Housetel a payment was approved, declined or voided.',
        webhook: true,
      },
      {
        title: 'Test in Sandbox',
        body: 'Save with the Sandbox environment, press "Test connection" and make a test booking on your booking engine paying with the card 4242 4242 4242 4242.',
      },
      {
        title: 'Go live',
        body: 'Once Wompi approves your account, switch the environment to Production and replace the four keys with the production ones.',
      },
    ],
    keys: [
      { field: 'public_key', where: 'Developers › API keys (starts with pub_test_ or pub_prod_)' },
      { field: 'private_key', where: 'Developers › API keys (starts with prv_test_ or prv_prod_)' },
      { field: 'integrity_secret', where: 'Developers › Secrets for technical integration › Integrity' },
      { field: 'events_secret', where: 'Developers › Secrets for technical integration › Events' },
    ],
    docsSection: '1. Pagos en línea: Wompi',
  },
  channel_channex: {
    provider: 'Channex',
    account: { label: 'Create a Channex staging account', href: 'https://staging.channex.io/' },
    environments: {
      sandboxLabel: 'Staging',
      sandbox: 'staging.channex.io: test properties, OTAs and bookings, without touching real sales.',
      productionLabel: 'Production',
      production: 'app.channex.io: your real channels (Booking.com, Expedia…). Requires your commercial account with Channex.',
    },
    steps: [
      {
        title: 'Create a Channex staging account',
        body: 'It is the free test environment to connect a PMS without touching real bookings.',
        link: { label: 'staging.channex.io', href: 'https://staging.channex.io/' },
      },
      {
        title: 'Create your property and copy its ID',
        body: 'In Properties create the hotel with its room types and rate plans. The ID (a UUID) is on the property\'s detail page.',
      },
      {
        title: 'Generate an API key',
        body: 'In Profile › API keys create a key for Housetel and paste it below together with the property ID.',
      },
      {
        title: 'Match room types and rates in Channels',
        body: 'Save here and open Channels › Connect › Channex: pair each Housetel room type and plan with Channex\'s. Housetel sends availability and rates, and downloads bookings every 5 minutes.',
      },
      {
        title: 'Connect your OTAs inside Channex',
        body: 'Booking.com, Expedia and the other channels are connected in Channex. To go live switch the environment and API key to app.channex.io.',
      },
    ],
    note: 'Channex certifies each PMS integration before production: for a pilot, use iCal or the channel manager the hotel already has.',
    keys: [
      { field: 'property_id', where: 'Channex › Properties › your hotel (property ID)' },
      { field: 'api_key', where: 'Channex › Profile › API keys' },
    ],
    docsSection: '4. Canales: Channex (staging)',
  },
  channel_ical: {
    provider: 'iCal',
    account: null,
    environments: null,
    note: 'No new account needed: you use the calendars Airbnb, VRBO or Booking.com already give you.',
    steps: [
      {
        title: 'Switch to real mode',
        body: 'In real mode Housetel downloads your listing sites\' calendars over HTTPS every 15 minutes (simulated mode only reads Housetel\'s own).',
      },
      {
        title: 'Copy the listing\'s export link',
        body: 'On Airbnb, VRBO or Booking.com look for the option to sync or export each listing\'s calendar (.ics) and copy the link.',
      },
      {
        title: 'Paste it in Channels',
        body: 'In Channels › Connect › iCal paste the link on the matching room type or room. Every booking from the site blocks those dates in Housetel.',
      },
      {
        title: 'Take Housetel\'s calendar to the site',
        body: 'Copy that connection\'s export URL in Channels and paste it as an imported calendar on the site, so it never sells dates that are already taken.',
      },
    ],
    keys: [],
    docsSection: '5. Calendarios iCal',
  },
  einvoice: {
    provider: 'Factus',
    account: { label: 'About Factus (technology provider)', href: 'https://www.factus.com.co/' },
    environments: {
      sandboxLabel: 'Sandbox',
      sandbox: 'Test invoices with no tax validity, to try the integration and the DIAN test set.',
      productionLabel: 'Production',
      production: 'Invoices valid before the DIAN with your numbering resolution. Requires the enablement to be finished.',
    },
    steps: [
      {
        title: 'Enable your company as an e-invoicer',
        body: 'In the DIAN\'s "Facturando electrónicamente" service register your company and choose Factus as your technology provider.',
        link: { label: 'dian.gov.co', href: 'https://www.dian.gov.co/' },
      },
      {
        title: 'Request the numbering resolution',
        body: 'Ask the DIAN for the e-invoicing resolution (prefix and range) and record it in Housetel\'s legal settings.',
      },
      {
        title: 'Ask Factus for your API credentials',
        body: 'Factus provides a client ID, client secret, user and password, first for its sandbox and, once enabled, for production.',
      },
      {
        title: 'Test in Sandbox',
        body: 'Save with the Sandbox environment, press "Test connection" and issue an invoice from the Legal tab of an in-house booking.',
      },
      {
        title: 'Go live',
        body: 'Once enabled, switch the environment to Production, update the credentials and, if Factus gave you any, the range IDs.',
      },
    ],
    keys: [
      { field: 'client_id', where: 'API credentials provided by Factus' },
      { field: 'client_secret', where: 'API credentials provided by Factus' },
      { field: 'username', where: 'The e-mail you sign in to Factus with' },
      { field: 'password', where: 'Your Factus user\'s password' },
      { field: 'numbering_range_id', where: 'Factus › numbering ranges (empty: the active resolution\'s)' },
    ],
    docsSection: '2. Factura electrónica DIAN: Factus',
  },
  tra: {
    provider: 'MinCIT (TRA)',
    account: { label: 'Request the MinCIT PMS token', href: 'https://pms.mincit.gov.co/token/' },
    environments: null,
    note: 'MinCIT has no test environment: in real mode every check-in files a real TRA.',
    steps: [
      {
        title: 'Have your current RNT at hand',
        body: 'The token is requested with the property\'s National Tourism Registry number. Also enter it in the hotel profile.',
      },
      {
        title: 'Request the PMS token',
        body: 'At pms.mincit.gov.co/token request the integration token for your RNT.',
        link: { label: 'pms.mincit.gov.co/token', href: 'https://pms.mincit.gov.co/token/' },
      },
      {
        title: 'Paste it here and test the connection',
        body: 'Save it as "RNT PMS token" and press "Test connection".',
      },
      {
        title: 'Check the registrations',
        body: 'Every check-in sends the TRA of the booker and companions. Legal › TRA shows each guest\'s status and lets you retry.',
      },
    ],
    keys: [
      { field: 'token', where: 'pms.mincit.gov.co/token, with the property\'s RNT' },
      { field: 'establishment_id', where: 'Your RNT number (empty: the hotel profile\'s)' },
    ],
    docsSection: '6. TRA (Tarjeta de Registro Hotelero, MinCIT)',
  },
  sire: {
    provider: 'Migración Colombia (SIRE)',
    account: { label: 'Migración Colombia SIRE portal', href: 'https://apps.migracioncolombia.gov.co/sire/' },
    environments: null,
    note: 'SIRE has no API for hotels: Housetel builds the file and you upload it on the portal.',
    steps: [
      {
        title: 'Register the property in SIRE',
        body: 'Migración Colombia gives you a SIRE user and the establishment code.',
      },
      {
        title: 'Fill in the codes in the legal settings',
        body: 'The establishment and city codes go on every line of the file.',
      },
      {
        title: 'Generate the file',
        body: 'The daily automation (08:00) builds the file with yesterday\'s foreigners\' check-ins and check-outs; you can also generate it in Legal › SIRE.',
      },
      {
        title: 'Upload it and mark it as reported',
        body: 'Upload it through SIRE\'s bulk upload and mark the report in Housetel with the receipt number.',
      },
    ],
    keys: [],
    docsSection: '7. SIRE (Migración Colombia)',
  },
  whatsapp: {
    provider: 'Meta (WhatsApp Cloud API)',
    account: { label: 'Open Meta for Developers', href: 'https://developers.facebook.com/apps/' },
    environments: {
      sandboxLabel: 'Test number',
      sandbox: 'Meta gives you a test number that only writes to the numbers you verify (up to 5).',
      productionLabel: 'Your number',
      production: 'The hotel\'s number, verified by Meta, with your tier\'s messaging limits.',
    },
    steps: [
      {
        title: 'Set up your Meta Business portfolio',
        body: 'Verify your business in Meta Business Suite: you need it to use the hotel\'s number.',
        link: { label: 'business.facebook.com', href: 'https://business.facebook.com/' },
      },
      {
        title: 'Create a Business app with WhatsApp',
        body: 'In Meta for Developers › My apps create the app and add the WhatsApp product.',
      },
      {
        title: 'Register the number and copy its ID',
        body: 'In WhatsApp › API setup add the hotel\'s number (it cannot stay active in the WhatsApp app) and copy its Phone number ID.',
      },
      {
        title: 'Create a permanent token',
        body: 'In Business settings › System users create a user, assign it the app and generate a token with whatsapp_business_messaging and whatsapp_business_management.',
      },
      {
        title: 'Save here, then subscribe the webhook',
        body: 'First save the Phone number ID, the token and a verify token you make up in Housetel (Meta checks it against the hotel already in real mode). Then, in WhatsApp › Configuration › Webhook, paste the URL below with that same token and subscribe to the messages field.',
        webhook: true,
      },
      {
        title: 'Get your templates approved',
        body: 'More than 24 hours after the guest\'s last message only Meta-approved templates can be sent, in Spanish and English.',
      },
    ],
    keys: [
      { field: 'phone_number_id', where: 'WhatsApp › API setup' },
      { field: 'access_token', where: 'Business settings › System users › Generate token' },
      { field: 'app_secret', where: 'Your app › Settings › Basic › App secret' },
      { field: 'verify_token', where: 'You make it up: the same text here and in Meta\'s webhook' },
    ],
    docsSection: '3. WhatsApp: WhatsApp Cloud API (Meta)',
  },
  email: {
    provider: 'SMTP',
    account: null,
    environments: null,
    note: 'With nothing configured, e-mails go out from Housetel\'s server with your hotel\'s name.',
    steps: [
      {
        title: 'Choose the sender',
        body: 'To send from your domain (bookings@yourhotel.com) create an SMTP account with a transactional e-mail provider (Amazon SES, Postmark, Brevo…).',
      },
      {
        title: 'Set up SPF, DKIM and DMARC',
        body: 'Add the records your provider gives you to your domain\'s DNS. Without them e-mails land in spam or bounce.',
      },
      {
        title: 'Enter the server details',
        body: 'The provider\'s server, port (587 with TLS), user and password, and a sender address on your domain.',
      },
      {
        title: 'Test the connection',
        body: 'Press "Test connection" and send yourself a test booking confirmation.',
      },
    ],
    keys: [
      { field: 'smtp_host', where: 'Provider panel › SMTP credentials' },
      { field: 'smtp_username', where: 'Provider panel › SMTP credentials' },
      { field: 'smtp_password', where: 'Provider panel › SMTP credentials' },
      { field: 'from_email', where: 'An address on your domain, verified with the provider' },
    ],
    docsSection: '8. Correo transaccional (SMTP con SPF y DKIM)',
  },
  llm: {
    provider: 'Gemini / Claude',
    account: { label: 'Create a Google AI Studio key', href: 'https://aistudio.google.com/apikey' },
    environments: {
      sandboxLabel: 'Free tier',
      sandbox: 'The platform key or your own without billing: few requests a day; when they run out the assistant keeps going in simulated mode.',
      productionLabel: 'With billing',
      production: 'Your Gemini key with Google Cloud billing, or a Claude key: more quota and no interruptions.',
    },
    steps: [
      {
        title: 'Start with the platform key',
        body: 'By default the AI uses Housetel\'s key, with a quota shared among hotels.',
      },
      {
        title: 'Use your own Gemini key',
        body: 'Create a key in Google AI Studio and, for more quota, turn on billing for its Google Cloud project.',
        link: { label: 'aistudio.google.com', href: 'https://aistudio.google.com/apikey' },
      },
      {
        title: 'Or connect Claude',
        body: 'Create a key in Anthropic\'s console, choose Claude as the provider and paste it below.',
        link: { label: 'console.anthropic.com', href: 'https://console.anthropic.com/' },
      },
      {
        title: 'Test it',
        body: 'Press "Test connection" and ask the copilot a question.',
      },
    ],
    keys: [{ field: 'api_key', where: 'Google AI Studio › Get API key, or Anthropic\'s console › API keys' }],
    docsSection: '9. IA de pago: Gemini y Claude',
  },
}

export function guideFor(kind: IntegrationKind, lang: Lang): IntegrationGuide | null {
  return (lang === 'en' ? EN : ES)[kind] ?? null
}

/** Where the long guide lives in the repository (linked when no documentation URL is configured). */
export const DOCS_PATH = 'docs/integraciones-reales.md'

/** Hosts the outside world cannot call back (webhooks need a public URL: a tunnel in development). */
export function isLocalUrl(url: string): boolean {
  try {
    const host = new URL(url).hostname.toLowerCase()
    return (
      host === 'localhost' ||
      host.endsWith('.localhost') ||
      host.endsWith('.local') ||
      host === '0.0.0.0' ||
      host === '::1' ||
      host === '[::1]' ||
      /^127\./.test(host) ||
      /^10\./.test(host) ||
      /^192\.168\./.test(host) ||
      /^172\.(1[6-9]|2\d|3[01])\./.test(host)
    )
  } catch {
    return true
  }
}

/** `https://tunnel.example` + `/api/v1/…` without doubling the slash. */
export function webhookUrlFor(base: string, path: string): string {
  return `${base.replace(/\/+$/, '')}${path}`
}

/** The command that opens a public tunnel to the development app (Cloudflare, no account needed). */
export const TUNNEL_COMMAND = 'cloudflared tunnel --url http://localhost:5173 --http-host-header localhost:5173'
