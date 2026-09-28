# Integraciones reales: dejar de simular

Housetel trae cada integración externa en dos modos: **simulado** (para demos y desarrollo: nada sale del sistema) y
**real**. Esta guía explica cómo pasar cada proveedor a real, paso a paso, primero en sus ambientes de prueba
(sandbox) y después en producción.

Todo se configura por hotel en **Configuración → Integraciones** (`/app/settings/integrations`, permiso
`control.integrations`): cada tarjeta tiene el interruptor **Real | Simulado**, el formulario de llaves (los secretos se
guardan cifrados y nunca se vuelven a mostrar), **Probar conexión** y la URL de webhook lista para copiar.

---

## 0. Antes de empezar

### 0.1 Apagar las simulaciones de la instalación

| Dónde | Qué hacer | Qué cambia |
|---|---|---|
| Producción (`DJANGO_ENV=production`) | Nada: vienen apagadas (`HOUSETEL_ALLOW_SIMULATIONS=0`) | Pasarela de pago simulada y simuladores de OTAs y WhatsApp → 404 y fuera del menú; sin banner "Entorno de demostración"; toda integración nueva arranca **en real y desactivada** hasta que tenga sus credenciales (se activa sola al completarlas) |
| Desarrollo (tu máquina) | `HOUSETEL_ALLOW_SIMULATIONS=0` en `.env` y recrea los servicios: `docker compose up -d backend worker beat` | Lo mismo, pero el entorno sigue siendo "development" (debug, Mailpit) |

Con las simulaciones apagadas, una integración que siga en modo simulado **falla con un mensaje claro** ("… está en
modo simulado y las simulaciones están desactivadas en este entorno") en vez de fingir un pago o una factura, y el modo
"Simulado" ya no se puede elegir (ni en la app ni por la API). Email y la IA son la excepción: conservan su modo (email
real por SMTP; la IA cae al asistente simulado si no hay clave o se agota la cuota).

Mientras un proveedor real no esté configurado, lo automático **espera en vez de fallar**:

| Qué | Sin configurar | Cuando lo configuras |
|---|---|---|
| Factura electrónica al check-out | No se numera ni se envía: queda en *Legal → Pendientes → Facturas* (emitirla a mano responde "La facturación electrónica no está configurada…") | La emites desde Pendientes o la pestaña Legal; las salidas de los últimos 3 días las emite `compliance.issue_pending_invoices` |
| TRA al check-in | El registro queda *Pendiente* con "La integración TRA no está configurada…" (sin gastar intentos) | `compliance.tra_retry` envía los de la última semana |
| Pagos en línea | El checkout del marketplace y del motor solo ofrecen "Pagar en el hotel"; el portal no muestra "Pagar" | Links de pago, portal y checkout cobran por Wompi |
| Cobro de la suscripción de Housetel (`saas.billing_cycle`) | Sin `WOMPI_PLATFORM_*` (o con el cobro desactivado en `/admin/billing`) **no cobra ni marca mora** a ninguna organización: la corrida queda "omitida" | Cobra renovaciones y pruebas vencidas como siempre |

### 0.2 La URL pública y el túnel para probar webhooks en local

Wompi, Meta (WhatsApp) y las OTAs necesitan llegar a tu instalación desde internet. La URL que se usa para los
webhooks y para los enlaces que reciben los huéspedes es `PUBLIC_BASE_URL` (si no está, `FRONTEND_URL`). La app la
muestra en cada tarjeta de Integraciones y la expone en `GET /api/v1/public/core/config/` (`public_base_url`).

En producción es tu dominio (`https://app.tuempresa.co`). En tu máquina, abre un túnel de Cloudflare hacia el servidor
de Vite:

```bash
# https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/
cloudflared tunnel --url http://localhost:5173 --http-host-header localhost:5173
# → "Your quick Tunnel has been created! Visit it at: https://<algo>.trycloudflare.com"
```

1. Copia la URL `https://<algo>.trycloudflare.com` en `.env` como `PUBLIC_BASE_URL=https://<algo>.trycloudflare.com`.
2. Recrea `backend`, `worker` y `beat` para que lean el `.env`: `docker compose up -d backend worker beat`.
3. Comprueba: `curl https://<algo>.trycloudflare.com/api/v1/public/core/config/` → `public_base_url` es la del túnel.

Notas: `--http-host-header localhost:5173` hace que Vite acepte las peticiones del túnel; ese origen queda en
`CSRF_TRUSTED_ORIGINS` automáticamente, así que también puedes usar la app completa por el túnel (p. ej. desde el
celular). Un túnel rápido cambia de URL cada vez que lo abres: vuelve a registrar los webhooks. Para una URL fija,
crea un túnel con nombre sobre tu dominio (`cloudflared tunnel create …`).

### 0.3 Orden recomendado para un hotel piloto

1. Correo (SMTP con SPF/DKIM) → 2. Wompi sandbox → 3. WhatsApp → 4. TRA → 5. Factus sandbox → 6. iCal o el channel
manager del hotel → 7. el día del lanzamiento, cambiar Wompi y Factus a producción. SIRE es manual desde el primer día.

---

## 1. Pagos en línea: Wompi (tarjeta, PSE, Nequi)

**Cuenta**: crea el comercio del hotel en <https://comercios.wompi.co> (Wompi es de Bancolombia). El sandbox está
disponible al registrarte; producción, cuando Wompi aprueba la documentación del comercio (RUT, cámara de comercio,
certificación bancaria de la cuenta donde recibirá el dinero).

**Llaves** (panel de Wompi → *Desarrolladores*; hay un juego para sandbox y otro para producción):

| Campo en Housetel | En Wompi | Formato |
|---|---|---|
| Ambiente | — | `Sandbox (pruebas)` o `Producción` |
| Llave pública | Llaves del API | `pub_test_…` / `pub_prod_…` |
| Llave privada (secreto) | Llaves del API | `prv_test_…` / `prv_prod_…` (consulta, anula y reembolsa) |
| Secreto de integridad (secreto) | Secretos para integración técnica | `test_integrity_…` / `prod_integrity_…` (firma el checkout) |
| Secreto de eventos (secreto) | Secretos para integración técnica | `test_events_…` / `prod_events_…` (valida los webhooks) |

**URL de eventos (webhook)**: en *Desarrolladores → URL de eventos* del mismo ambiente pon

```
{PUBLIC_BASE_URL}/api/v1/public/finance/webhooks/wompi/
```

**En Housetel**: Integraciones → **Pagos en línea** → Real → llena los cinco campos → Guardar → **Probar conexión**
("Conectado a Wompi…"). Con las llaves completas la integración queda activa y los links de pago, el portal del
huésped ("Pagar"), el check-in online, el motor de reservas y el marketplace cobran por Wompi.

**Probar en sandbox**: crea un link de pago desde el folio de una reserva y págalo con los datos de prueba de la
documentación de Wompi (<https://docs.wompi.co/docs/colombia/datos-de-prueba-en-sandbox/>; p. ej. la tarjeta
`4242 4242 4242 4242` aprueba y la `4111 1111 1111 1111` rechaza). Al volver, el pago aparece en el folio; si el
webhook no llegó (túnel apagado), la automatización `finance.sync_pending_intents` lo verifica cada 5 minutos.

**Producción**: cambia *Ambiente* a Producción y reemplaza las cuatro llaves por las `prod`, registra la URL de eventos
en el ambiente de producción de Wompi y haz un pago real pequeño (y su reembolso desde el folio).

> Cobro de la suscripción de Housetel (plataforma): usa la cuenta Wompi de Housetel con las variables
> `WOMPI_PLATFORM_*` del servidor y el webhook `{PUBLIC_BASE_URL}/api/v1/public/saas/webhooks/wompi/`
> (super-admin → `/admin/billing`).

---

## 2. Factura electrónica DIAN: Factus

Housetel emite a través de **Factus**, proveedor tecnológico autorizado por la DIAN (API v2).

**Requisitos del hotel ante la DIAN** (los hace el hotel o su contador):

1. RUT con la responsabilidad de **facturador electrónico** y firma electrónica vigente.
2. **Habilitación** en el portal de la DIAN (*Factura electrónica → Habilitación*), eligiendo a Factus como
   proveedor tecnológico, y aprobación del set de pruebas (Factus acompaña este paso).
3. **Resolución de numeración** (formulario 1876 en los servicios en línea de la DIAN): prefijo, rango (desde–hasta),
   vigencia y **clave técnica**. Asóciala al hotel en Factus.

**Cuenta Factus**: crea la cuenta en <https://www.factus.com.co>. Para pruebas pide las credenciales del **sandbox**
(<https://developers.factus.com.co>, API `https://api-sandbox.factus.com.co`); producción usa otras credenciales.

| Campo en Housetel (Integraciones → **Factura electrónica DIAN** → Real) | Qué es |
|---|---|
| Ambiente | Sandbox o Producción |
| Client ID / Client secret (secreto) | Credenciales OAuth de la API de Factus |
| Usuario / Contraseña (secreto) | El usuario de Factus (el token dura 1 h y Housetel lo renueva solo) |
| ID del rango de numeración | Opcional: vacío = el de la resolución activa o el único rango activo en Factus |
| ID del rango de notas crédito | Opcional |
| Enviar la factura por correo desde Factus | Opcional |

Mientras Factus no esté configurado (modo real sin credenciales o desactivado), Housetel **no numera ni envía**
facturas: las salidas quedan en *Legal → Pendientes → Facturas* y no se gasta ningún número de la resolución.

**En Housetel, además**: *Configuración → Legal Colombia* (`/app/settings/compliance`): razón social, NIT y RNT del
emisor (perfil del hotel) y la **resolución** (prefijo, rango, vigencia, clave técnica, ambiente). **Probar conexión**
lista los rangos de Factus. Con la emisión automática activada, cada check-out genera y valida su factura; las que
fallan quedan en *Legal → Pendientes* y la automatización `compliance.issue_pending_invoices` las reintenta cada 15
minutos. Emite primero en sandbox (con la resolución de pruebas) y revisa el PDF, el CUFE y el XML antes de pasar a
producción.

---

## 3. WhatsApp: WhatsApp Cloud API (Meta)

**Cuenta**: el hotel necesita un portafolio de **Meta Business** (<https://business.facebook.com>), idealmente
verificado, y un número que **no** esté usando la app de WhatsApp (o migrarlo).

1. En <https://developers.facebook.com> crea una **app de tipo Empresa** y agrega el producto **WhatsApp**.
2. En *WhatsApp → Configuración de la API* agrega el número del hotel, verifícalo con SMS o llamada y configura el
   nombre visible (Meta lo aprueba). Copia el **Phone number ID** (no es el número de teléfono).
3. **Token permanente**: en *Configuración del negocio → Usuarios del sistema* crea un usuario del sistema
   administrador, asígnale la app y la cuenta de WhatsApp y genera un token sin vencimiento con los permisos
   `whatsapp_business_messaging` y `whatsapp_business_management`. (El token temporal de la página de la API vence en
   24 h: solo sirve para una prueba rápida.)
4. **App secret**: en la app, *Configuración → Básica → Clave secreta de la app*.
5. Inventa un **token de verificación** (cualquier texto largo), p. ej. `housetel-casa-aurora-7f3a…`.

**En Housetel** (hazlo **antes** del webhook: Meta lo verifica contra el hotel que ya está en modo real): Integraciones
→ **WhatsApp** → Real → Phone number ID, Token de acceso, App secret, Token de verificación (y, si tus plantillas
aprobadas usan otro código de idioma, `es`/`en_US`) → Guardar → **Probar conexión** (muestra el número y el nombre
verificado).

**Webhook** (app de Meta → *WhatsApp → Configuración → Webhook*):

```
URL de devolución de llamada: {PUBLIC_BASE_URL}/api/v1/public/messaging/webhooks/whatsapp/
Token de verificación:        el mismo que guardaste en Housetel
Campos:                       messages
```

**Plantillas**: fuera de la ventana de 24 h desde el último mensaje del huésped, WhatsApp solo deja enviar
**plantillas aprobadas** (categoría *Utilidad*: confirmación de reserva, link de check-in, link de pago…). Créalas en
*WhatsApp Manager → Plantillas* y asígnalas en *Configuración → Mensajería* (`/app/settings/messaging`) a cada
mensaje automático. Prueba: escribe al número del hotel desde tu celular → el hilo aparece en la **Bandeja**
(`/app/inbox`) → responde desde Housetel.

---

## 4. Canales: Channex (staging)

Channex conecta Booking.com, Expedia y más de 50 OTAs. Úsalo primero en su **staging**:

1. Crea una cuenta en <https://staging.channex.io>, la propiedad, sus tipos de habitación y planes tarifarios.
2. Copia el **ID de la propiedad** (UUID, en el detalle de la propiedad) y genera una **API key** (*Perfil → API
   keys*).
3. En Housetel: *Canales* (`/app/channels`) → **Conectar canal** → Channex → modo Real → Ambiente `staging`, ID de
   la propiedad y API key → mapea cada categoría y plan con los de Channex (la lista sale de la API de Channex) →
   **Conectar Channex** → en la tarjeta, **Sincronizar todo**. Las tarifas y la disponibilidad se envían solas al cambiar; las reservas se descargan
   cada 5 minutos (`distribution.pull_bookings`) y se confirman en Channex.
4. Prueba: crea una reserva de prueba en el staging de Channex → llega al PMS como reserva de OTA.

**Producción**: Channex exige **certificar** la integración de cada PMS antes de abrir producción (pruebas de ARI por
rangos, volumen de actualizaciones, webhooks). Mientras Housetel no esté certificado, para un piloto usa **iCal** o el
channel manager que el hotel ya tenga.

---

## 5. Calendarios iCal (Airbnb, VRBO, Booking.com para alojamientos tipo casa)

iCal no pide llaves: en producción ya viene en modo real. Por cada portal:

1. **Importar al PMS**: en el extranet del portal copia la URL de exportación del calendario (Airbnb: *Calendario →
   Disponibilidad → Conectar calendarios → Exportar*) y pégala en *Canales → Conectar canal → iCal* (una conexión por
   portal) en la categoría o habitación correspondiente. Housetel la descarga cada 15 minutos (o **Importar ahora**).
2. **Exportar al portal**: copia la URL `…/api/v1/public/distribution/ical/<token>.ics` de esa habitación (botón
   **Copiar URL**) y pégala en el portal (Airbnb: *Importar calendario*).

Limitaciones propias de iCal: solo bloquea fechas (sin precios ni datos del huésped) y cada portal lo lee a su ritmo
(Airbnb puede tardar horas), así que existe riesgo de doble venta en fechas muy demandadas. Housetel solo descarga URLs
HTTPS públicas (bloquea redes internas).

---

## 6. TRA (Tarjeta de Registro Hotelero, MinCIT)

1. El hotel necesita su **RNT** activo (Registro Nacional de Turismo) en el perfil (`/app/settings/property`).
2. Pide el **token PMS** del establecimiento en <https://pms.mincit.gov.co/token/> con ese RNT.
3. En Housetel: Integraciones → **TRA · MinCIT** → Real → Token (el identificador del establecimiento, vacío = el RNT del
   perfil; la URL del servicio viene con `https://pms.mincit.gov.co`) → Guardar → **Probar conexión**.
4. Cada check-in registra al titular y a sus acompañantes (con los datos del check-in online); los registros con datos
   faltantes o errores quedan en *Legal → TRA* y `compliance.tra_retry` los reintenta cada 15 minutos. Antes de
   configurar la TRA, los check-ins dejan sus registros *Pendientes* ("La integración TRA no está configurada") y se
   envían solos cuando la actives (los de la última semana).

Nota: MinCIT no publica una especificación estable del servicio; la URL base y las rutas (`/one/`, `/two/`) son
configurables por si cambian. Confirma con MinCIT el host vigente antes del lanzamiento.

---

## 7. SIRE (Migración Colombia) — carga manual

Migración Colombia no ofrece API: el reporte se sube en su portal.

1. El hotel se inscribe en SIRE (<https://apps.migracioncolombia.gov.co/sire/>) y obtiene su usuario.
2. En *Configuración → Legal Colombia* pon el **código del establecimiento en SIRE** y la ciudad (código DIVIPOLA).
3. Cada día a las 08:00 la automatización `compliance.sire_daily_file` prepara el archivo del día anterior con las
   entradas y salidas de extranjeros. En *Legal → SIRE* → **Descargar TXT** → súbelo en el portal (*Alojamiento y
   hospedaje → Cargar archivo*) → vuelve a Housetel y **Marca como reportado** (con el número de acuse si lo tienes).

---

## 8. Correo transaccional (SMTP con SPF y DKIM)

Sin autenticación de dominio, los correos de Housetel (confirmaciones, links de check-in y de pago, recuperación de
contraseña) terminan en spam.

1. Elige un proveedor transaccional (Amazon SES, Postmark, SendGrid, Brevo, Mailgun) y **verifica el dominio**
   remitente (p. ej. `housetel.co` o el del hotel).
2. Publica en el DNS del dominio los registros que te da el proveedor:
   - **SPF** (TXT en la raíz): `v=spf1 include:<dominio-del-proveedor> ~all` — un solo registro SPF por dominio.
   - **DKIM**: los CNAME/TXT de firma del proveedor.
   - **DMARC** (TXT en `_dmarc`): empieza con `v=DMARC1; p=none; rua=mailto:dmarc@tu-dominio` y sube a
     `p=quarantine` cuando los reportes estén limpios.
3. En el servidor (`.env.prod`): `EMAIL_HOST`, `EMAIL_PORT` (587), `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`,
   `EMAIL_USE_TLS=1` y `DEFAULT_FROM_EMAIL="Housetel <no-reply@tu-dominio>"` (el dominio verificado).
4. Por hotel (opcional), Integraciones → **Correo electrónico** → remitente propio, *Responder a* (por defecto el correo del hotel,
   así las respuestas de los huéspedes le llegan a él) o un SMTP propio.
5. Prueba: envía un correo a <https://www.mail-tester.com> desde la Bandeja y apunta a 9/10 o más.

**Correos de cuenta** (restablecer la contraseña, confirmar el correo y el aviso de contraseña cambiada): salen de
Housetel, no del hotel, desde `DEFAULT_FROM_EMAIL`, y sus enlaces usan `PUBLIC_BASE_URL` (o `FRONTEND_URL`). Los dos
tienen que ser los reales del servidor para que el equipo del hotel piloto pueda recuperar su acceso; pruébalo con
*¿Olvidaste tu contraseña?* en `/login` antes del lanzamiento. Las invitaciones al equipo usan el mismo remitente.

En desarrollo el correo va a Mailpit (<http://localhost:8025>) y no sale de tu máquina.

---

## 9. IA de pago: Gemini y Claude

La IA (copiloto, chatbot, onboarding, resúmenes de revenue) usa **Gemini** por defecto. La cuota gratuita
(`gemini-3.5-flash`, unas 20 solicitudes al día, compartida por todos los hoteles de la instalación) se agota rápido; al
agotarse todo sigue funcionando con el asistente simulado.

- **Gemini**: crea la clave en <https://aistudio.google.com> y **activa la facturación** del proyecto de Google Cloud
  asociado (sube los límites). En el servidor: `GEMINI_API_KEY` (y `GEMINI_MODEL`). Un hotel puede usar su propia
  clave en Integraciones → **Asistente de IA** (campo *API key*).
- **Claude**: crea la clave en <https://console.anthropic.com> y carga créditos. En el servidor: `ANTHROPIC_API_KEY`
  (y `CLAUDE_MODEL`). Cada hotel elige el proveedor en *Configuración → IA* (`/app/settings/ai`) o en Integraciones.
- **Costos**: el copiloto hace al menos 2 llamadas por pregunta; las corridas programadas de revenue piden el resumen IA
  solo una vez al día (`ai_summary_once_a_day`). `/app/settings/ai` muestra el uso por función.

---

## 10. Checklist de salida a producción de un hotel

- [ ] Correo: SPF, DKIM y DMARC publicados; prueba en mail-tester ≥ 9/10.
- [ ] Wompi en producción: pago real pequeño aprobado y reembolsado; webhook de producción registrado.
- [ ] WhatsApp: número verificado, token permanente, webhook suscrito a `messages`, plantillas de utilidad aprobadas.
- [ ] TRA: un check-in real registrado en MinCIT.
- [ ] Factus en producción con la resolución real: primera factura validada por la DIAN (revisa el CUFE en el
      catálogo de la DIAN).
- [ ] SIRE: código del establecimiento y primer archivo cargado en el portal.
- [ ] Canales: iCal o channel manager probado con una reserva de prueba y su cancelación.
- [ ] En *Integraciones* ninguna tarjeta queda en simulado y "Probar conexión" da correcto en todas.
