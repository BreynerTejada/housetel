# Housetel — Plan de la Fase P (piloto real)

> Ejecución: un Workflow (`housetel-phase-p`) con 6 implementadores en paralelo (P1–P6) → integración P-INT. **Modo MVP (decisión del usuario):** no se escriben ni corren tests en esta fase. Después vienen la validación en Chrome del orquestador y una fase de tests dedicada.

**Goal:** Cerrar las brechas que impiden un piloto con hoteles reales, según la auditoría `docs/audit/2026-09-28-auditoria-vs-cloudbeds.md` y la validación en Chrome:
- producción segura;
- cuentas completas;
- reservas multi-habitación y grupos;
- facturación corporativa;
- importador;
- integraciones reales guiadas;
- pulido de UX, i18n, accesibilidad y aspectos legales.

**Base:** spec `docs/superpowers/specs/2026-09-25-housetel-pms-design.md` y plan original `docs/superpowers/plans/2026-09-25-housetel-implementation.md` (reglas §B, contratos §C, extensiones §E), más las notas `docs/integration-notes/*.md` (sobre todo C-INT.md).

## Reglas de esta fase

- **Modo MVP.**
  - No escribas tests nuevos ni corras suites. No arregles tests viejos que se rompan (tampoco los borres).
  - Verificación mínima obligatoria:
    - `manage.py check`;
    - migraciones de tu app al día;
    - curl a tus endpoints principales con el seed (login con CSRF, ver `backend/scripts/smoke_proxy.py`);
    - typecheck y eslint filtrados a tus archivos.
- **Propiedad estricta de archivos.** Cada tarea lista sus owner paths. Las excepciones a nivel de archivo están escritas explícitamente; fuera de eso, no toques nada ajeno. Si necesitas algo de otra tarea, usa los contratos de abajo o anótalo en tus notas para P-INT.
- **Las apps nuevas `corporate` e `imports` ya existen** (esqueleto registrado en `LOCAL_APPS`, permisos `corporate.view|manage|ar` e `imports.run`, roles actualizados). No toques `config/settings.py` salvo P1.
- **Seeds, señales y paralelismo.** Receivers con `if is_seeding(): return`. Seed de cada app < 60 s, probado con rollback. **No corras `seed_demo`.** No uses el navegador compartido (MCP chrome-devtools / claude-in-chrome). No uses `docker compose down` ni reinicies servicios compartidos (P1 puede levantar el stack de producción en otros puertos con otro nombre de proyecto: `-p housetel-prod`).
- **i18n, UI y documentación.**
  - i18n ES/EN completo; responsive a 375 px; UI con el sistema de diseño existente.
  - Documenta en `docs/integration-notes/P<n>-*.md` con la plantilla del plan original §B más la sección **"Cómo probarlo en la UI"**.
- **Secretos.** El `.env` no se toca ni se imprime. No hagas commits.

## Contratos nuevos de esta fase

Las firmas son exactas. P1 las implementa en `core`; las demás tareas las consumen:

```python
# apps/core/runtime.py (P1)
def environment() -> str                       # "development" | "production" (env DJANGO_ENV)
def simulations_enabled() -> bool               # False en producción salvo HOUSETEL_ALLOW_SIMULATIONS=1
def require_simulations(view_func)              # decorador: 404 si simulations_enabled() es False
def public_base_url() -> str                    # env PUBLIC_BASE_URL (p. ej. un túnel cloudflared) o FRONTEND_URL
def support_contact() -> dict                   # {"whatsapp": str, "email": str, "docs_url": str} desde el entorno

# apps/core/integrations.py (P1, agregado)
def is_live(property, kind: str) -> bool        # True si la integración está enabled, en modo real y configurada
```

`GET /api/v1/public/core/config/` (P1, público) devuelve:

```json
{"environment": "...", "simulations_enabled": true, "public_base_url": "...", "support": {}}
```

En el frontend, P1 lo expone como `useRuntimeConfig()` en `src/lib/runtime.ts`. `NavItem` gana el campo opcional `devOnly?: boolean` (ítems ocultos si `simulations_enabled` es false).

---

## P1 — Producción, seguridad, soporte y modo real

**Owner paths:**
- `backend/config/**`, `backend/apps/core/**`, `backend/requirements.txt`.
- `docker-compose.prod.yml`, `deploy/**` (nginx, gunicorn, Dockerfiles de producción), `scripts/**` (backup y restore), `.github/workflows/**`, `Makefile`, `.env.example`, `docs/deploy.md`, `docs/integraciones-reales.md`.
- `frontend/src/app/**` **excepto** `frontend/src/app/pages/LoginPage.tsx` (es de P2), `frontend/src/lib/**`.
- Excepción de archivo: `backend/apps/accounts/api/*` **no** (es de P2).

**Requisitos:**
1. **Settings por entorno con `DJANGO_ENV`.** En producción:
   - Falla al arrancar si `DEBUG` está activo o no hay `SECRET_KEY` o `FERNET_KEY`.
   - `ALLOWED_HOSTS` y `CSRF_TRUSTED_ORIGINS` vienen del entorno.
   - `SECURE_PROXY_SSL_HEADER`, `SECURE_SSL_REDIRECT` y HSTS (1 año, subdominios, preload).
   - Cookies de sesión y CSRF `Secure`; `SESSION_COOKIE_HTTPONLY`; `SECURE_CONTENT_TYPE_NOSNIFF`; `Referrer-Policy`; `X_FRAME_OPTIONS=DENY` en la API.
   - `NUM_PROXIES` de DRF desde el entorno (los throttles por IP deben funcionar detrás de nginx).
   - Logs JSON.
   - `/django-admin/` detrás de `ADMIN_ENABLED` y solo para staff; `/api/schema/` y `/api/docs/` solo para staff (en desarrollo quedan como hoy).
   - Swagger servido offline con `drf-spectacular-sidecar`.
2. **`docker-compose.prod.yml`:**
   - Postgres y Redis con volúmenes.
   - Backend con **gunicorn** (workers configurables), worker y beat.
   - **nginx** que sirve el frontend compilado (build multi-etapa), hace proxy de `/api`, sirve `/static` y las fotos públicas de `/media` (`/media/photos/**`), y **nunca** los documentos privados.
   - En nginx, CSP razonable, gzip y cache de assets con hash.
   - Healthchecks y `restart: unless-stopped`.
   - Targets `make prod-build` y `make prod-up` (proyecto `housetel-prod`, puerto `8080` por defecto).
   - Verifica que construye y levanta, y apágalo al terminar.
3. **Almacenamiento privado configurable:**
   - Disco local privado (default) o S3-compatible (`django-storages` + `boto3`) si hay variables `AWS_*`.
   - Fotos públicas y documentos privados en storages separados.
4. **Monitoreo:**
   - Sentry opcional (`sentry-sdk`, solo si hay `SENTRY_DSN`).
   - `GET /api/v1/public/core/health/ready/` que revisa BD y Redis (503 si fallan).
5. **Backups:**
   - `scripts/backup.sh`: `pg_dump -Fc` + tar de media privada y pública, con marca de tiempo, retención N días y subida opcional a S3.
   - `scripts/restore.sh`.
   - Targets `make backup` y `make restore FILE=...`.
   - `docs/deploy.md` con la recomendación de PITR y Postgres administrado.
6. **CI** en `.github/workflows/ci.yml`:
   - Backend: ruff y pytest con servicios postgres y redis, con `-m "not live_llm"`.
   - Frontend: typecheck, lint, test y build.
   - Queda escrito, no hace falta ejecutarlo.
7. **Runtime y modo real:**
   - Contratos de arriba. En producción, `integrations.default_mode` pasa a `real`, con la integración deshabilitada hasta configurarla.
   - `get_provider` rechaza `simulated` (lanza `IntegrationNotAvailable`) salvo `simulations_enabled()`.
   - Email y LLM conservan su comportamiento.
   - Agrega `PUBLIC_BASE_URL` y `SUPPORT_*` a `.env.example`.
8. **Soporte:**
   - Ítem "Ayuda y soporte" en el menú de usuario del shell: panel con WhatsApp, email y enlace a documentación, tomados de `support_contact`.
   - El ErrorBoundary y la 404 muestran cómo contactar soporte.
9. **Portal y errores de API:**
   - Los tokens del portal vencen: `make_reservation_token` incluye `exp` = checkout + 30 días y `read_reservation_token` lo verifica. Los tokens sin `exp` (anteriores) siguen válidos.
   - Errores de API traducidos: `LocaleMiddleware` + idioma del usuario o `Accept-Language`. El `NotFound` de DRF sale en español.
10. **`NavItem.devOnly`:**
    - Filtrado en `src/app/extensions.ts` según `useRuntimeConfig().simulations_enabled`.
    - Banner discreto "Entorno de demostración" en el shell cuando las simulaciones están activas y el entorno no es producción.
11. **Guía de integraciones reales:** `docs/integraciones-reales.md`, paso a paso por proveedor:
    - Wompi sandbox y producción (llaves, eventos, URL de webhook `{PUBLIC_BASE_URL}/api/v1/public/finance/webhooks/wompi/`);
    - Factus sandbox y producción (habilitación DIAN, resolución);
    - WhatsApp Cloud (Meta Business, número, token, verify token, app secret, webhook);
    - Channex staging;
    - iCal;
    - TRA (RNT, token);
    - SIRE (carga manual);
    - SMTP transaccional (SPF/DKIM);
    - Gemini y Claude de pago;
    - túnel local con `cloudflared tunnel --url http://localhost:5173` y `PUBLIC_BASE_URL`.

## P2 — Cuentas: contraseña y verificación de email

**Owner paths:** `backend/apps/accounts/**`, `frontend/src/features/team/**`. Excepción de archivo: `frontend/src/app/pages/LoginPage.tsx` (solo agregar el enlace "¿Olvidaste tu contraseña?").

**Requisitos:**
1. **Olvidé mi contraseña:**
   - `POST /api/v1/public/accounts/password/forgot/` `{email}`: responde siempre 200 (sin enumeración de usuarios), con throttle.
   - Email ES/EN, según el idioma del usuario, con enlace `${FRONTEND_URL}/reset-password/<uidb64>/<token>` (`PasswordResetTokenGenerator`).
2. **Restablecer:**
   - `POST /api/v1/public/accounts/password/reset/` `{uid, token, new_password}`: aplica los validadores de Django.
   - Invalida las demás sesiones (el hash de sesión cambia) e inicia sesión.
3. **Cambiar contraseña:** `POST /api/v1/accounts/me/password/` `{current_password, new_password}` conserva la sesión actual (`update_session_auth_hash`).
4. **Verificación de email:**
   - `User.email_verified_at` (migración). Una data migration marca como verificados a los usuarios existentes.
   - Receiver `post_save` de User creado (con `is_seeding` guard) que envía el email de verificación, salvo usuarios creados por invitación (se marcan verificados al aceptar).
   - `POST /api/v1/public/accounts/verify-email/` `{token}` (firmado, 7 días).
   - `POST /api/v1/accounts/me/verify-email/resend/`.
   - `Me` incluye `email_verified`.
5. **Frontend** (feature `team`):
   - Páginas públicas `/forgot-password`, `/reset-password/:uid/:token`, `/verify-email/:token`.
   - `/app/settings/account` "Mi cuenta y seguridad": cambiar contraseña, estado de verificación y reenviar.
   - `topbar.tsx` con un chip "Verifica tu correo" si falta verificar.
   - Enlace en LoginPage.

## P3 — Reservas multi-habitación, grupos y cupos

**Owner paths:** `backend/apps/bookings/**`, `backend/apps/frontdesk/**`, `frontend/src/features/frontdesk/**`. No toques `features/calendar`.

**Requisitos:**
1. **Asistente multi-habitación:**
   - En el paso Tarifa, cantidad por oferta (+/−) y mezcla de categorías. En dormitorios, cantidad = camas.
   - Reparto de adultos y niños por habitación.
   - El resumen muestra cada habitación y su precio.
   - El payload manda N `StayRequest`.
   - Mantén el arreglo de exención de IVA por titular extranjero (`bookerIsForeignNonResident`, ya en `lib/wizard.ts`).
2. **Estadías en reservas existentes:**
   - Agregar habitación: `POST /api/v1/bookings/reservations/{id}/stays/` con la oferta.
   - Nuevo servicio `cancel_stay(stay, *, reason, waive_fee=False, actor=None) -> Reservation`: penalidad proporcional según la política; si es la última estadía activa, cancela la reserva. Endpoint `POST /stays/{id}/cancel/` `{reason, waive_fee, confirm}` + vista previa.
   - UI en el detalle de reserva.
3. **Grupos:**
   - `/app/groups`: lista con nombre, fechas, habitaciones, pickup y saldo.
   - Detalle: rooming list (estadías de todas las reservas del grupo, con nombres por habitación editables en línea), reservas del grupo y agregar reserva al grupo.
   - En el asistente, conmutador "Reserva de grupo": crea el `ReservationGroup` y la reserva con N habitaciones.
4. **Cupos (allotments):**
   - Nuevo modelo `GroupBlock(group, room_type, start, end, units, release_date, released_at)`: retiene inventario (vía `InventoryDay.blocked_units` o un contador propio coherente con `availability` y `rebuild_inventory`).
   - Pickup: las estadías creadas "desde el cupo" consumen el bloqueo.
   - Automatización `bookings.release_group_blocks` (diaria) libera lo no tomado en la `release_date`.
   - UI en el detalle del grupo.
5. **Check-in con habitación ocupada:** `check_in` responde `RoomNotReadyError` con `code="room_occupied"` (409) si otra estadía **en casa** ocupa la habitación, salvo `force`. La auto-asignación ya lo evita.
6. **Aterrizaje por rol:** sin `frontdesk.view` → `housekeeping.work` va a `/app/housekeeping/mine`, `reports.*` va a `/app/reports`, y el resto al primer ítem de su menú. En el móvil del panel Hoy, los nombres ocupan hasta 2 líneas (sin cortarse tan pronto).

## P4 — Facturación corporativa y cartera

**Owner paths:** `backend/apps/corporate/**` (ya registrada), `backend/apps/finance/**`, `backend/apps/compliance/**` **excepto** `backend/apps/compliance/services/sire.py` (es de P6), `frontend/src/features/corporate/**` (nueva), `frontend/src/features/finance/**`, `frontend/src/features/compliance/**`.

**Requisitos:**
1. **`Company`** (por organización):
   - Campos: razón social, nombre comercial, NIT + DV (valida el dígito de verificación), responsable o no de IVA, responsabilidades fiscales DIAN, dirección, ciudad, email de facturación, teléfono, crédito habilitado, cupo, plazo en días, contactos, notas, activa.
   - CRUD `/api/v1/corporate/companies/`.
   - UI `/app/companies` (lista y detalle con estado de cuenta).
2. **`ReservationBilling`** (1-1 con la reserva, en `corporate`):
   - `bill_to` `guest|company`, `company`, reglas de enrutamiento por tipo de cargo (alojamiento, impuestos del alojamiento, extras, todo), número de orden de compra, notas.
   - UI como pestaña de reserva "Facturación" (`reservation-tabs.tsx` de la feature `corporate`).
3. **Folios divididos:**
   - Finance soporta folio del huésped + folio de la empresa por reserva.
   - `post_charge` enruta según `corporate.services.target_folio(reservation, kind)`.
   - Transferir cargos entre folios (con auditoría) y dividir un cargo.
   - `FolioPanel` muestra pestañas por folio.
   - `reservation_balance` excluye lo que va a la empresa con crédito (el check-out del huésped no se bloquea por eso).
4. **Factura a la empresa:**
   - Una factura por folio. El folio de la empresa sale a su NIT (razón social, DV, responsabilidades) y el del huésped al huésped.
   - En la pestaña Legal: selector "Facturar a" y emisión por folio.
5. **Cartera (cuentas por cobrar):**
   - Folios de empresa con saldo → cartera.
   - Estado de cuenta con antigüedad 0–30, 31–60, 61–90 y 90+.
   - Registrar pago a cuenta, aplicado a facturas o folios.
   - `/app/companies/:id` con el estado de cuenta y `/app/receivables` con el resumen.
6. **Sims de pago:** aplica `core.runtime.require_simulations` a las vistas públicas de pago simulado de finance.
7. **Seed:** 3 empresas (una agencia de viajes y dos corporativos), 5 reservas facturadas a empresa, un folio dividido y cartera con antigüedades variadas.

## P5 — Importador (migración desde otro PMS)

**Owner paths:** `backend/apps/imports/**` (ya registrada), `frontend/src/features/imports/**` (nueva).

**Requisitos:**
1. **Import jobs** (`ImportJob`, `ImportRow`):
   - Subir CSV o XLSX. Tipos: huéspedes, reservas (futuras y en casa) y, opcionalmente, categorías y habitaciones.
2. **Mapeo de columnas:**
   - Autodetección de encabezados ES/EN.
   - Presets: **genérico** y **export de Cloudbeds** (investiga su formato de export de reservas y huéspedes).
   - Mapeo de valores desconocidos (categoría y plan).
3. **Vista previa y ejecución:**
   - Validación por fila (errores y advertencias), dry-run y ejecución en Celery con progreso.
   - Idempotencia por (sistema de origen, id externo): reimportar actualiza o salta.
   - Reporte de errores descargable (CSV).
   - Plantillas descargables ES/EN.
4. **Reservas:**
   - Contratos `guests.services.upsert_guest` + `bookings.services.reservations.create_reservation(source="import", enforce_restrictions=False)`.
   - Los conflictos de disponibilidad son errores de fila; no se sobrevende.
   - Asigna habitación si viene el número.
   - Estado `checked_in` para reservas en casa (mediante el servicio `check_in` con force).
   - Montos pagados → `finance.services.record_payment(method="other", reference="Saldo importado")`.
5. **Revertir importación:** cancela y marca las reservas creadas por el job que no tengan actividad posterior, con auditoría.
6. **UI** `/app/settings/import`:
   - Asistente tipo → subir → mapear → revisar → importar → resultado.
   - Historial de jobs.
   - Permiso `imports.run`.

## P6 — Pulido de UX, i18n, accesibilidad, legal, Habeas Data e integraciones guiadas

**Owner paths** (a nivel de archivo donde se indica):
- `frontend/src/design/**`.
- `frontend/src/features/{ai,marketplace,calendar,control,saas,channels,messaging,guestportal,revenue}/**`.
- `backend/apps/{marketplace,revenue,ai,distribution,messaging,guests,guestportal}/**`.
- Excepción: `backend/apps/compliance/services/sire.py` (solo textos).

**Requisitos:**
1. **Móvil:**
   - La burbuja del chatbot no tapa botones a 375 px: se desplaza o compacta en `/g/*` y `/book/*`, o respeta un área segura.
   - Checkout móvil (`/book/:slug`): el resumen del total queda visible arriba o sticky antes del botón "Confirmar".
2. **Textos:**
   - Plurales correctos en `sire.py` ("1 movimiento", "1 archivo").
   - Las alertas se muestran traducidas en el frontend: mapeo por `kind` a clave i18n con `data`; si no existe, el texto guardado.
   - El título de `/search` con capitalización correcta.
3. **Contraste AA:** ajusta el token `text-subtle` (claro y oscuro) a ≥4,5:1 sobre sus fondos.
4. **Bugs de Chrome:**
   - Etiqueta del mes del calendario sin solaparse.
   - La explicación de revenue usa el precio final redondeado (y dice que redondea).
   - El onboarding IA deduplica extras equivalentes (desayuno).
   - El aviso de "Ejecutar ahora" en automatizaciones queda visible con el resultado aunque la corrida sea instantánea.
5. **Simuladores:**
   - `devOnly: true` en los nav de los simuladores (channels, messaging).
   - `require_simulations` en los endpoints de simulador de messaging y distribution.
   - Opciones BookSim/AirSim ocultas si las simulaciones están apagadas.
   - Checkout (marketplace): si `integrations.is_live(property, "payments")` es falso en producción, solo ofrece "Pagar en el hotel" y lo marca por defecto.
6. **Seguridad iCal:** la protección SSRF resuelve DNS y bloquea IPs privadas, link-local y loopback, también tras redirecciones.
7. **Legal:**
   - Páginas públicas `/legal/terminos`, `/legal/privacidad` (política de tratamiento de datos, Ley 1581) y `/legal/encargo-datos` (DPA hotel ↔ Housetel), en ES/EN.
   - Las casillas de consentimiento del checkout, el check-in online y el signup enlazan a ellas.
8. **Retención Habeas Data:** automatización `guests.purge_identity_documents` que borra fotos de documentos y firmas N días después del checkout (default 180, configurable por propiedad, 0 = nunca) y registra lo borrado en la auditoría.
9. **Integraciones guiadas** (feature `control`): cada tarjeta de Integraciones muestra una guía paso a paso del proveedor:
   - qué cuenta crear y enlace oficial;
   - dónde está cada llave;
   - sandbox vs producción;
   - la **URL de webhook** (con `public_base_url`) lista para copiar;
   - un aviso si la URL es `localhost` (sugiere el túnel);
   - enlace a `docs/integraciones-reales.md`.
   - El texto "7 de 9 en simulado" pasa a una llamada a la acción: "Activa los modos reales".

## P-INT — Integración de la Fase P (sin tests)

1. Aplica los "cambios requeridos" de las notas P1–P6.
2. `makemigrations --check`; migrate desde una BD nueva.
3. `seed_demo --reset` completo en segundo plano (el seed de P4 y P3 agrega empresas, grupos y cupos) y `make check-data`.
4. Frontend typecheck, lint y build.
5. `make smoke` (amplíalo con 3–4 pasos de esta fase) y el barrido de endpoints.
6. Prueba de producción: `make prod-build && make prod-up` en otro puerto y proyecto → la health responde, el frontend compilado carga, `/django-admin/` está bloqueado, `/api/docs/` pide staff, el endpoint de pago simulado da 404 y los simuladores no aparecen en el menú. Luego `make prod-down`.
7. Escribe `docs/integration-notes/P-INT.md` con el checklist consolidado "Cómo probar en la UI" de esta fase para la validación en Chrome. Deja el stack de desarrollo arriba con el seed.
