# P1 — Producción, seguridad, soporte y modo real — integration notes

Estado (2026-09-28, modo MVP: sin tests nuevos ni suites): **los 11 requisitos del plan implementados y verificados**.
El stack de producción (`docker-compose.prod.yml`, proyecto `housetel-prod`, puerto 8080) **se construyó, se levantó
con todos los servicios *healthy*, se probó por HTTP y con Chrome headless propio, se hizo backup y restauración de
punta a punta y se apagó** (`down -v`: no quedan contenedores ni volúmenes `housetel-prod_*`; las imágenes
`housetel-backend:prod` y `housetel-web:prod` quedan construidas para P-INT). El stack de desarrollo sigue arriba y
sin cambios de comportamiento (simulaciones activas, docs y admin abiertos). `.env` intacto, sin commits.

Respuesta corta a "¿hay una forma de dejar de simular y traer información real?": **sí**. En producción las
simulaciones vienen apagadas; en local basta `HOUSETEL_ALLOW_SIMULATIONS=0` (+ un túnel `cloudflared` y
`PUBLIC_BASE_URL` para recibir webhooks). Cada proveedor se conecta en *Configuración → Integraciones* siguiendo la
guía nueva [`docs/integraciones-reales.md`](../integraciones-reales.md) (Wompi, Factus, WhatsApp Cloud, Channex,
iCal, TRA, SIRE, SMTP con SPF/DKIM, Gemini/Claude de pago). Despliegue: [`docs/deploy.md`](../deploy.md).

---

## API implementada

Todas públicas (sin sesión), en `apps/core/public_urls.py`.

| Método y path | Respuesta |
|---|---|
| `GET /api/v1/public/core/health/` | (ya existía) `{"status":"ok"}`: liveness, sin BD |
| `GET /api/v1/public/core/health/ready/` | **Nuevo.** 200 `{"status":"ok","checks":{"database":{"ok":true,"ms":10.7},"redis":{"ok":true,"ms":37.0}}}`; si PostgreSQL o Redis fallan → **503** `{"status":"error","checks":{"database":{"ok":true,…},"redis":{"ok":false,"ms":2001.3}}}` (el motivo solo va al log `housetel.health`). `Cache-Control: no-store`. Exento de la redirección a HTTPS (healthchecks por http) |
| `GET /api/v1/public/core/config/` | **Nuevo.** `{"environment":"development"\|"production","simulations_enabled":true,"public_base_url":"http://localhost:5173","support":{"whatsapp":"","email":"soporte@housetel.co","docs_url":""}}`. `Cache-Control: no-cache` (el SPA lo pide una vez por carga de página). Es lo que lee `useRuntimeConfig()` |

Cambios de comportamiento en endpoints existentes:

| Qué | Desarrollo | Producción |
|---|---|---|
| `/api/schema/`, `/api/docs/` | públicos (como hoy) | anónimo → 401, usuario sin `is_staff` → 403, staff → 200. Swagger servido **offline** con `drf-spectacular-sidecar` (en cualquier entorno donde el paquete esté instalado) |
| `/django-admin/` | como hoy (con su login) | no existe (`ADMIN_ENABLED=0`, 404). Con `ADMIN_ENABLED=1`, 404 para todo el que no sea staff con sesión (el formulario de login del admin nunca se expone; el staff entra por `/login` de la app) |
| Errores de la API | traducidos: idioma del perfil del usuario con sesión, si no `Accept-Language` (el SPA lo manda con el idioma de la UI), si no `es` | igual |
| 404 de `get_object_or_404` ("No Reservation matches the given query.") | ahora `{"detail":"No encontrado.","code":"not_found"}` (o "Not found." en inglés) | igual |
| Vistas con `require_simulations` (P4 ya lo aplicó a `sim/intents/…` de finance) | como hoy | 404 `{"detail":"No encontrado.","code":"not_found"}` |
| Tokens del portal (`/g/<token>` y APIs públicas que lo usan) | incluyen `exp` = check-out + 30 días; los tokens sin `exp` (anteriores) siguen valiendo | igual |

Verificado por curl contra `http://localhost:5173/api/...` (login con cookie jar + CSRF de `owner@casaaurora.co`):
`/core/config/` 200, `/core/health/ready/` 200 (BD 20 ms, Redis 96 ms la primera), `/core/context/` 200, reserva
inexistente → 404 "No encontrado." (el perfil del dueño es `es`: gana sobre `Accept-Language: en`), anónimo con
`Accept-Language: en` en `/accounts/me/` → 401 "Authentication credentials were not provided.", `/api/docs/` 200 y
`/django-admin/login/` 200 en desarrollo.

## Contratos implementados / consumidos

Firmas exactas del plan (P1 las implementa; P2–P6 ya las consumen: P4 `require_simulations`, P6 `useRuntimeConfig`,
`devOnly`, `whatsappLink`/`mailtoLink`):

```python
# apps/core/runtime.py
def environment() -> str                # "production" si DJANGO_ENV=production; si no "development"
def simulations_enabled() -> bool       # HOUSETEL_ALLOW_SIMULATIONS=1/0 manda; sin él: True salvo en producción
def require_simulations(view_func)      # 404 JSON {"detail","code":"not_found"} si simulations_enabled() es False.
                                        # Sirve en funciones (@api_view), clases (envuelve dispatch), métodos
                                        # (method_decorator) y en SomeView.as_view() dentro de urls.py
def public_base_url() -> str            # settings.PUBLIC_BASE_URL o FRONTEND_URL, sin "/" final
def support_contact() -> dict           # {"whatsapp", "email", "docs_url"} (SUPPORT_*; "" = no se ofrece)
def public_config() -> dict             # cuerpo de GET /public/core/config/

# apps/core/integrations.py (agregado)
def is_live(property, kind: str) -> bool   # enabled + modo real + sin requeridos faltantes; no crea la fila
```

Extras de `apps/core/integrations.py` (para P-INT/control):
- `mode_allowed(kind, mode) -> bool` y `available_modes(kind) -> list[str]`: con simulaciones apagadas solo `real`
  (email y llm conservan `simulated`).
- `default_enabled(kind, mode=None) -> bool`: el `enabled` con el que nace una fila (para listar tarjetas sin fila).
- `missing_fields(provider_cls, config, secrets)` / `missing_required(setting, *, mode=None)`: requeridos faltantes
  (mismo criterio que el centro de control: un select obligatorio sin default usa su primera opción) + variables de
  entorno obligatorias de proveedores de plataforma (`REQUIRED_DJANGO_SETTINGS`: `saas_billing` real necesita
  `WOMPI_PLATFORM_PUBLIC_KEY/PRIVATE_KEY/INTEGRITY_SECRET`).
- `SIMULATION_EXEMPT_KINDS = {"email", "llm"}`.

Reglas nuevas del framework de integraciones (sin cambiar firmas):
- `default_mode(kind)`: email → `real`; llm → `real` si hay `GEMINI_API_KEY` (igual que antes); el resto →
  `simulated` con simulaciones activas, **`real` con simulaciones apagadas**.
- `get_setting` crea la fila con ese modo y `enabled = default_enabled(...)`: con simulaciones apagadas, un proveedor
  real que exige credenciales nace **deshabilitado** (pagos, Channex, DIAN, TRA, WhatsApp, cobro SaaS sin llaves); iCal,
  SIRE, email y la IA nacen activos.
- `set_secrets` **activa sola** una integración real deshabilitada cuando esas credenciales completan su
  configuración (solo con simulaciones apagadas; si ya estaba completa y alguien la apagó a mano, sigue apagada).
- `get_provider` lanza `IntegrationNotAvailable` (400 `integration_not_available`, con `kind` y `mode`) si la fila está
  en `simulated` y el modo no está permitido; el respaldo al simulado cuando falta el proveedor del modo solo ocurre
  si el simulado está permitido.

Verificado en el contenedor de producción (transacción revertida): pagos real/deshabilitado/no vivo; configurar
Wompi en dos pasos → activo y `is_live` solo al completar el cuarto secreto; rotar una llave con la integración
apagada a mano → sigue apagada; `mode="simulated"` → `integration_not_available`.

Otros contratos tocados:
- `core.tokens`: `make_reservation_token` agrega `exp` (ISO, check-out + `PORTAL_TOKEN_DAYS_AFTER_CHECKOUT` = 30);
  `read_reservation_token` devuelve `None` si `exp` pasó (fecha local de Bogotá); `token_expiry(reservation)` nuevo;
  `portal_url` usa `public_base_url()` (idéntico a `FRONTEND_URL` mientras no haya `PUBLIC_BASE_URL`).
- `apps.core.api.exceptions`: el `Http404` sin mensaje o con el texto por defecto de Django sale como el `NotFound`
  traducido de DRF; los `Http404("mensaje propio")` conservan su mensaje.
- Middleware nuevo en `settings.MIDDLEWARE`: `django.middleware.locale.LocaleMiddleware`,
  `apps.core.middleware.UserLanguageMiddleware` (idioma del perfil, solo si hay cookie de sesión) y
  `apps.core.middleware.AdminGateMiddleware`.
- `apps.core.storage` (nuevo): `settings.STORAGES` tiene los alias `default` (media pública), `private` (archivos
  privados: `LocalPrivateStorage` = `PRIVATE_MEDIA_ROOT` o `<MEDIA_ROOT>-private`, sin URL; o S3 privado) y
  `staticfiles`. `PrivateStorage()` es un proxy `@deconstructible` al alias `private` para usar en `FileField`
  (`url()` lanza ValueError como hoy); `private_media_root()`, `private_storage()`.
- `apps.core.logs.JsonFormatter` (logs JSON con `request_id`, `exc_info` y los `extra=`).
- `manage.py create_platform_admin [--email] [--name] [--password-env VAR]`: crea o promueve un super-admin
  (`is_platform_admin` + `is_staff` + `is_superuser`); `make prod-createsuperuser` lo usa (el `createsuperuser` de
  Django no pone `is_platform_admin`).

## Señales emitidas / escuchadas

Ninguna.

## Automatizaciones registradas

Ninguna nueva.

## Proveedores de integración registrados

Ninguno. Cambian las reglas de `get_provider`/`get_setting` (arriba).

## Extensiones de frontend exportadas (widgets, tabs, topbar, commands)

Ninguna de §E. Piezas nuevas:

| Archivo | Qué es |
|---|---|
| `src/lib/runtime.ts` | `useRuntimeConfig()` (TanStack Query `['runtime-config']`, `staleTime: Infinity`; mientras carga o si falla devuelve `FALLBACK_RUNTIME_CONFIG` = valores de producción, así un simulador nunca parpadea en el menú de un hotel real; agrega `loaded`), tipos `RuntimeConfig`/`SupportContact`, `fetchRuntimeConfig`, `isDemoEnvironment(config)`, `whatsappLink(phone, text?)`, `mailtoLink(email, subject?, body?)`, `hasSupportChannel(support)` |
| `src/app/extensions.ts` | `NavItem.devOnly?: boolean`; `filterNav(items, {can, isPlatformAdmin, simulationsEnabled = true})`; `useNav` pasa `simulations_enabled` (sidebar, configuración, admin, paleta ⌘K y el aterrizaje por menú quedan filtrados) |
| `src/app/shell/DemoBanner.tsx` | Franja rayada (el `.hatch` de las habitaciones fuera de servicio: "no es lo real") sobre la barra superior de `AppLayout` y `AdminLayout`, solo con `simulations_enabled && environment !== 'production'`; con `control.integrations` ofrece "Activa los modos reales →" (`/app/settings/integrations`). Se va con el scroll (la barra sigue fija). A 375 px: solo "Entorno de demostración" + "Modos reales" |
| `src/app/shell/SupportDialog.tsx` + ítem "Ayuda y soporte" (`LifeBuoy`) en `UserMenu` | Canales como "llaveros" del casillero (perforación a la izquierda; WhatsApp destacado). Cada enlace abre el canal con el mensaje ya escrito: hotel, usuario, pantalla (sin tokens ni query string) y hora. Bloque "Van incluidos en tu mensaje" con **Copiar datos**. El foco inicial va al primer canal |
| `src/app/shell/SupportLinks.tsx`, `src/app/shell/support.ts` | Línea de soporte bajo la 404 (`NotFound`, pública y de los shells) y el error de ruta (`RouteError`, que además agrega el error al mensaje). `useSupportContext` lee `me` de la caché: nunca pide `/accounts/me/` en páginas públicas |
| `src/lib/api.ts` | Manda `Accept-Language` con el idioma de la UI (`<html lang>`) en toda petición |
| `src/lib/auth.tsx` | `Me.email_verified?: boolean` (para el chip de P2); las queries `['me']` y `['runtime-config']` sobreviven al cambio de propiedad y al logout |
| `src/lib/i18n/locales/{es,en}/common.json` | `support.*` y `demoBanner.*` (paridad ES/EN verificada: 230 claves) |

Validado en Chrome headless propio (perfil y puerto aparte, nunca el navegador compartido) a 1440 y 375 px, claro y
oscuro, ES y EN (páginas públicas), contra desarrollo y contra el build de producción en :8080: sin excepciones, sin
violaciones de CSP, sin scroll horizontal; en producción no aparecen banner ni simuladores. `tsc` limpio (todo el
proyecto salvo tests ajenos de `features/frontdesk/__tests__`) y `eslint src/app src/lib` limpio.

## Dependencias nuevas (pip/npm) y por qué

`backend/requirements.txt` (sección "Production"; el plan las pide explícitamente):

| Paquete | Por qué |
|---|---|
| `gunicorn>=26.2.0,<27` | Servidor WSGI de producción (`config/gunicorn_conf.py`: workers/threads/timeout por entorno, `gthread`, `max_requests` con jitter) |
| `drf-spectacular-sidecar>=2026.9.1` | Swagger UI/Redoc sin CDN |
| `django-storages[s3]>=1.14.6,<2`, `boto3>=1.43.103,<2` | Almacenamiento S3 compatible |
| `sentry-sdk[django,celery]>=2.70.0,<3` | Errores a Sentry si hay `SENTRY_DSN` |

Npm: ninguna. **La imagen de desarrollo no las tiene todavía**: `settings.py` las detecta (`find_spec`) y funciona
sin ellas (Swagger por CDN, sin S3, sin Sentry); la imagen de producción las instala. P-INT: `docker compose build
backend worker beat` para tenerlas en desarrollo.

## Cambios requeridos en archivos compartidos u otras apps (para P-INT)

1. **Centro de control (backend `apps/control/services/integrations.py`, sin dueño en la Fase P)** — en producción aún
   ofrece "Simulado" y muestra `enabled: true` para kinds sin fila:
   - `serialize()`: `"available_modes": integrations.available_modes(kind)` y
     `"enabled": setting.enabled if setting else integrations.default_enabled(kind)`.
   - `update()`: rechazar `mode` fuera de `integrations.available_modes(kind)` (400 "El modo simulado no está
     disponible en este entorno"). Hoy guardarlo "funciona" y luego `get_provider` falla con
     `integration_not_available` (seguro, pero confuso).
   - Mismo criterio en `apps/distribution/api/serializers.py:417` (modo de iCal/Channex; P6).
2. **Storages privados → S3.** Hoy los documentos privados siguen en disco local aunque haya `AWS_*`. Cambiar la base
   de `guests.storage.PrivateDocumentStorage` (P6), `compliance.storage.ComplianceStorage` (P4) y
   `housekeeping.storage.PrivateMediaStorage` (sin dueño) a `apps.core.storage.PrivateStorage` (conservando el nombre
   de la clase: las migraciones no cambian porque serializan la ruta de la subclase). Revisar después
   `makemigrations --check`. Todo lo lee con `.open("rb")`, compatible con S3.
3. **URLs para el mundo exterior**: usar `apps.core.runtime.public_base_url()` en vez de `settings.FRONTEND_URL` donde
   la URL la consume alguien fuera de la sesión del navegador: `distribution/services/ical.py::export_url` (P6: la URL
   `.ics` que importa Airbnb), `marketplace/services/checkout.py` (`return_url` de Wompi) y
   `marketplace/services/configuration.py` (URLs del motor/widget) (P6), `saas/api/admin_views.py:580`
   (`webhook_url`), y los enlaces de correos de `accounts` (P2). Con el túnel, esos enlaces funcionarían desde el
   celular del huésped o desde Meta/Wompi.
4. **Cobro SaaS en producción (riesgo)**: `saas.billing_cycle` cobra con Wompi de plataforma y, tras 3 intentos
   fallidos, **suspende** la organización. Sin llaves `WOMPI_PLATFORM_*` todos los intentos fallan. Propuesta: si
   `not integrations.is_live(None, "saas_billing")`, no cobrar ni pasar a `past_due`/`suspended` (registrar un aviso).
5. **Legal (P4)**: con `einvoice`/`tra` en real sin configurar (default de producción), la emisión automática al
   check-out y el registro TRA al check-in fallan contra Factus/MinCIT sin credenciales. Propuesta: si
   `not integrations.is_live(prop, "einvoice"|"tra")`, dejarlos en pendiente ("configura la integración") en vez de
   intentar.
6. **`frontend/vite.config.ts`**: agregar `'/static': { target, changeOrigin: false }` al proxy. Con el sidecar
   instalado (tras reconstruir la imagen de desarrollo), `/api/docs/` por el puerto 5173 necesita los estáticos de
   Django (por 8010 funciona siempre).
7. **`.gitignore`**: agregar `.env.prod` y `backups/` (la plantilla de producción está en `deploy/env.prod.example`).
8. **README**: enlazar `docs/deploy.md` y `docs/integraciones-reales.md`; comandos `make prod-build`, `prod-up`,
   `prod-down`, `prod-ps`, `prod-logs`, `prod-shell`, `prod-createsuperuser`, `prod-check`, `backup`,
   `restore FILE=...`.
9. **Reiniciar `worker` y `beat` de desarrollo** para que tomen el código de P1 (hoy solo `runserver` recarga solo).
10. **drf-spectacular (P5)**: `manage.py check --deploy` avisa W001 por dos `ConfirmSerializer` con el mismo nombre
    (`apps/imports/api/serializers.py` y `apps/guests/api/serializers.py`): renombrar el de imports.
11. **Tests (fase de tests)**: los tests de frontend que rendericen componentes con `useNav` (sidebar, configuración,
    paleta, Hoy) piden `GET /api/v1/public/core/config/`: agregar un handler por defecto en `src/test/server.ts`
    (`shell.test.tsx` y `router.test.tsx` ya lo cubren con `apiNotFoundFallback`). En backend, cubrir: fail-fast de
    producción, `require_simulations` (4 formas), tokens con `exp`, `is_live`/`default_enabled`/`set_secrets`, gate del
    admin y del esquema, `Accept-Language`/idioma del perfil y la 404 traducida.

## Limitaciones conocidas / pendientes

- **Modo MVP**: sin tests nuevos ni suites; los tests viejos de `apps/core` deberían seguir pasando (firmas intactas,
  desarrollo por defecto) pero no se corrieron.
- **Mensajes de dominio**: siguen en español fijo (el código los escribe así); solo los mensajes propios de Django/DRF
  (404, 401, 403, 429, validaciones de campos) salen en inglés con UI/perfil en inglés.
- **TLS**: el compose publica http en 8080; el TLS va delante (Caddy/balanceador; ejemplo en `docs/deploy.md`) o en
  nginx con un `server` 443 propio.
- **CSP**: `style-src 'unsafe-inline'` (Radix y sonner inyectan `<style>`); el script inline de `index.html` va por
  hash calculado al construir la imagen. `/embed/` permite `frame-ancestors *` (el widget se embebe en sitios de
  hoteles). Con fotos en S3 hay que agregar su dominio en `NGINX_CSP_IMG_SRC`.
- **Beat** no tiene healthcheck (se reinicia solo con `restart: unless-stopped`).
- **`NUM_PROXIES`** por defecto 1 (solo nginx). Detrás de Caddy/Cloudflare/balanceador hay que subirlo (documentado).
- **saas_billing y legal en producción**: ver cambios requeridos 4 y 5.
- **Backups**: la retención en S3 la define la regla de ciclo de vida del bucket; con S3 como storage, la media no está
  en el volumen (el tar sale vacío: activar versionado del bucket). La `FERNET_KEY` no va en el backup, a propósito.
- **Swagger en 5173** tras reconstruir la imagen de desarrollo: ver cambio requerido 6.
- **Canal Channex** no está certificado para producción (sin cambios en esta fase; la guía lo advierte).

---

## Verificación hecha

| Chequeo | Resultado |
|---|---|
| `docker compose exec -T backend python manage.py check` | "System check identified no issues" (dev) |
| Migraciones | `makemigrations core --check` → sin cambios (core no tiene modelos nuevos); global también limpio al momento |
| OpenAPI | `spectacular --validate --fail-on-warn` OK (tuve que dejar `environment` como string: un enum chocaba con otro `environment` nuevo de otra app) |
| Fail-fast de producción | sin claves → `ImproperlyConfigured: Production settings are incomplete: …`; `DJANGO_DEBUG=1` → falla; completo → `check --deploy` sin avisos de seguridad salvo W008 cuando se apaga la redirección para probar en http |
| `ruff check` + `ruff format --check` de `config/` y `apps/core/` | limpios |
| Frontend | `tsc -p tsconfig.app.json --noEmit` sin errores en `src/app` y `src/lib`; `eslint src/app src/lib` limpio |
| Seed | `seed_base` de core + seed de `control` sobre una propiedad nueva, en transacción revertida: 0,2 s, con simulaciones activas (todo simulado y probado, como antes) y apagadas (real, deshabilitado lo que exige llaves). Revertido: la org temporal no quedó |
| `make prod-build` | backend + nginx en 2 min 10 s (1.ª vez), 42 s después; hash CSP calculado |
| `make prod-up` (puerto 8080) | db, redis, backend, worker, beat, nginx *healthy* en ~40 s; `/healthz` 200, `health/ready` 200, `config` → `production` / `simulations_enabled: false` |
| Seguridad en :8080 | SPA con CSP, `X-Frame-Options SAMEORIGIN`, nosniff, `Referrer-Policy`, `Permissions-Policy`, COOP; `/embed/` con `frame-ancestors *`; assets `immutable` 1 año + gzip; `/django-admin/` 404 (y con `ADMIN_ENABLED=1`: staff 200, dueño/anónimo 404); `/api/docs/` anónimo 401, dueño 403, staff 200 con assets del sidecar desde `/static/`; `sim/intents/…` y `…/decide/` 404; `/media/photos/…` 200, rutas privadas y `..` → 404 o la SPA; throttle de login: 10 intentos → 429 aunque se falsee `X-Forwarded-For` |
| Flujo real en :8080 | `/signup` → hotel nuevo con sesión (cookies `Secure` en `http://localhost`), integraciones reales/deshabilitadas, `create_platform_admin`, logs JSON en backend/worker/beat/nginx con `request_id`, 0 errores en los logs |
| `make backup` / `make restore` | backup en 0,9 s (dump verificado + media pública y privada + sha256); se borró un usuario y archivos, `make restore FILE=… RESTORE_CONFIRM=yes` (30 s) los devolvió y el stack volvió *healthy* |
| `make prod-down` + `down -v` | stack de producción apagado y sus volúmenes borrados |

---

## Cómo probarlo en la UI

**Entorno de desarrollo** (http://localhost:5173, `owner@casaaurora.co` / `housetel123`):

1. **Banner de demostración**: al entrar a `/app` aparece arriba una franja rayada "**Entorno de demostración** ·
   Pagos, canales, facturación electrónica y WhatsApp funcionan en modo simulado: nada sale del sistema." y, a la
   derecha, **Activa los modos reales →** (lleva a `/app/settings/integrations`). Al hacer scroll la franja se va y
   la barra superior queda fija. Con `recepcion@casaaurora.co` el banner sale sin el enlace (no tiene
   `control.integrations`). A 375 px: "Entorno de demostración" + "Modos reales →". También en `/admin`
   (`admin@housetel.co`).
2. **Ayuda y soporte**: avatar (arriba a la derecha) → **Ayuda y soporte** → diálogo con los canales como llaveros.
   Con el `.env` actual solo sale **Correo** (`soporte@housetel.co`, el valor por defecto); con `SUPPORT_WHATSAPP` y
   `SUPPORT_DOCS_URL` en `.env` (y `docker compose up -d backend`) salen también **WhatsApp** (destacado) y **Guías**. Abajo,
   "Van incluidos en tu mensaje": Hotel Casa Aurora, Valentina Rojas · owner@casaaurora.co, Pantalla `/app`, fecha y
   hora → **Copiar datos** → toast "Datos copiados". El correo abre el cliente con el asunto "Ayuda con Housetel ·
   Hotel Casa Aurora" y esos datos en el cuerpo; WhatsApp abre `wa.me` con el mismo texto.
3. **404 con soporte**: `/app/esta-no-existe` → "No encontramos esta página" + "¿Llegaste aquí desde un enlace de
   Housetel? Avísanos:" con los enlaces de soporte. Igual en la parte pública (`/esta-no-existe`) y en inglés desde el
   selector de idioma. El error de pantalla (`RouteError`) muestra "¿Sigue fallando? Escríbenos y cuéntanos qué
   estabas haciendo:" y agrega el error al mensaje.
4. **Simuladores en el menú**: en desarrollo siguen en *Herramientas* (Simulador de OTAs, Simulador de WhatsApp: son
   `devOnly` de P6 y las simulaciones están activas).
5. **Errores traducidos** (se ven en la respuesta de la API; las pantallas suelen mostrar su propio texto i18n): abre
   `/app/reservations/00000000-0000-0000-0000-000000000000` con las herramientas de desarrollo → pestaña Red → la
   respuesta es `{"detail": "No encontrado.", "code": "not_found"}` (antes "No Reservation matches the given
   query."). Cambia tu idioma a **English** (menú de idioma: guarda el perfil), recarga → `"detail": "Not found."` y
   cabecera `Content-Language: en`. Vuelve a Español al terminar. Sin sesión manda `Accept-Language`: en `/login` con
   la UI en inglés, `GET /api/v1/accounts/me/` responde "Authentication credentials were not provided.".
6. **Links del portal que vencen**: un link de una reserva que salió hace más de 30 días ya no abre:
   ```bash
   docker compose exec -T backend python manage.py shell -c "from apps.core.tokens import portal_url; \
     from apps.bookings.models import Reservation; \
     print(portal_url(Reservation.objects.filter(checkout_date__lt='2026-08-25').first()))"
   ```
   → abre la URL → "Este enlace no es válido o ya no está disponible". Los links de reservas actuales
   (`manage.py portal_links --property casa-aurora --days 3`) siguen funcionando, y también los links viejos sin
   vencimiento que ya se habían enviado.
7. **Dejar de simular en local** (opcional; revertir después): agrega `HOUSETEL_ALLOW_SIMULATIONS=0` a `.env` y
   recrea los servicios (`docker compose up -d backend worker beat`) → recarga la app: sin banner, sin simuladores en el menú, la pasarela simulada `/sim/pay/<ref>`
   deja de funcionar (su API responde 404) y en Integraciones, **Probar conexión** en una tarjeta que sigue en
   simulado responde que las simulaciones están desactivadas en este entorno. Quita la línea y vuelve a correr
   `docker compose up -d backend worker beat` para volver a la demo.

**Stack de producción** (puerto 8080; no toca el de desarrollo):

```bash
scripts/prod-local-env.sh /tmp/housetel-prod.env 8080      # env desechable con claves al azar (docs/deploy.md §9)
make prod-build prod-up PROD_ENV_FILE=/tmp/housetel-prod.env
```

8. http://localhost:8080 → **Crea tu cuenta** (`/signup`) → hotel nuevo → `/app`: **sin** banner de demostración y
   **sin** simuladores en el menú; "Ayuda y soporte" muestra los `SUPPORT_*` del archivo de entorno.
9. *Configuración → Integraciones*: Pagos, Channex, DIAN, TRA y WhatsApp en **Real** (y, para quien tenga los cambios de
   P-INT en control, deshabilitadas hasta completar sus llaves); iCal, SIRE y Email en real y activas.
10. http://localhost:8080/api/docs/ → 401 sin sesión; con el super-admin (`make prod-createsuperuser`) → Swagger
    completo sin internet. http://localhost:8080/django-admin/ → 404.
11. `make backup PROD_ENV_FILE=…` → archivos en `backups/`; `make restore FILE=backups/housetel-<fecha>-db.dump
    PROD_ENV_FILE=…` → pide escribir RESTORE y restaura base y media.
12. `make prod-down PROD_ENV_FILE=…` (agrega `down -v` con el mismo comando de compose para borrar sus datos).

---

## Archivos

- Backend: `backend/config/{settings.py, urls.py, gunicorn_conf.py (nuevo)}`, `backend/requirements.txt`,
  `backend/apps/core/{runtime.py, storage.py, logs.py (nuevos), integrations.py, tokens.py, middleware.py,
  public_urls.py, api/views.py, api/exceptions.py, management/commands/create_platform_admin.py (nuevo)}`.
- Frontend: `frontend/src/lib/{runtime.ts (nuevo), api.ts, auth.tsx, i18n/locales/{es,en}/common.json}`,
  `frontend/src/app/{extensions.ts, layouts/AppLayout.tsx, layouts/AdminLayout.tsx, pages/NotFound.tsx,
  pages/RouteError.tsx, shell/UserMenu.tsx, shell/{DemoBanner.tsx, SupportDialog.tsx, SupportLinks.tsx,
  support.ts} (nuevos)}`.
- Despliegue: `docker-compose.prod.yml`, `deploy/backend/Dockerfile`, `deploy/nginx/{Dockerfile,
  templates/default.conf.template, templates/snippets/housetel-headers.conf.template,
  templates/snippets/housetel-proxy.conf.template}`, `deploy/env.prod.example`, `scripts/{backup.sh, restore.sh,
  prod-local-env.sh}`,
  `.github/workflows/ci.yml`, `Makefile` (targets `prod-*`, `backup`, `restore`), `.env.example`.
- Documentación: `docs/deploy.md`, `docs/integraciones-reales.md`, esta nota.
