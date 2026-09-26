# A3 — Verificación de la Fase A

Resultado: todo el checklist de A3 pasa. Hice 7 correcciones: un bug con pérdida de datos, un endpoint que el
checklist exige y aún no existía, más fidelidad de contratos y ruido en los logs y en los tests. Cada corrección
viene con su test visto en rojo primero. Todo se corrió en Docker Compose desde `/home/breyner/Documents/new_project`.
No modifiqué `.env` ni hice commits. El stack quedó arriba con datos de demo.

Leer primero: la sección "Qué cambia para las fases B/C". El resto documenta la evidencia.

---

## Qué cambia para las fases B/C

- **`Me` trae `phone`**: `GET/PATCH /api/v1/accounts/me/` devuelven
  `{id, email, full_name, language, phone, is_platform_admin, memberships}`. El tipo `Me` del frontend tiene
  `phone: string` y `makeMe()` lo incluye.
- **Nuevo endpoint con alcance de propiedad**: `GET /api/v1/core/context/`, con el encabezado `X-Property-Id`.
  Devuelve lo siguiente:
  ```json
  {"property": {"id", "name", "slug", "property_type", "timezone", "currency", "business_date"},
   "organization": {"id", "name", "slug", "status"},
   "role": {"id", "name", "code"},
   "permissions": ["*"]}
  ```
  - Las formas son las mismas que en `Me`.
  - Lo puede leer cualquier miembro con acceso a la propiedad.
  - Errores: 400 `property_required`, 404 `not_found`, 401 anónimo y 402 si la organización está suspendida.
  - Es el endpoint de referencia de `PropertyScopedAPIView`: ver `apps/core/api/views.py`.
- **Tipos de retorno fijados**: `apps/core/tests/test_contracts.py` también compara ahora las anotaciones de
  retorno de spec §4.2 / plan §C, por ejemplo `create_reservation -> Reservation` o
  `post_room_charges -> list[Charge]`.
  - Si implementas un stub, conserva la anotación. Se ignoran el prefijo de módulo y las comillas.
  - Si la anotación te obliga a un import circular, usa `from __future__ import annotations` y un import bajo
    `TYPE_CHECKING`, como en `bookings/services/charges.py`.
- **Helpers públicos en `apps.accounts.api.serializers`**: `organization_payload`, `role_payload`,
  `property_payload` y los serializers de documentación `OrganizationRef`, `RoleRef` y `PropertyRef`.
  Antes se llamaban `_OrganizationRef`, etc.
- **Formularios del frontend**: en `<Select>` de Radix dentro de un `<form>`, pasa `name={field.name}`. Si no, el
  `<select>` nativo oculto queda sin nombre y Chrome lo reporta como issue.
- **Tests del frontend**: el entorno de referencia es el contenedor (Node 24):
  `docker compose run --rm --no-deps frontend npx vitest run src/features/<feature>`. El `act(...)` corregido
  abajo solo aparecía ahí, no con Node 26 en el host.

---

## Lo verificado (checklist A3)

### 1. Stack desde cero

- Comando: `docker compose down -v && docker compose up -d --build`. Salida con exit 0 en 38 s, y en 23 s en la
  corrida final.
  - Levanta los 7 servicios. `db` y `mailpit` quedan `healthy`; `backend`, `worker`, `beat`, `frontend` y `redis`
    quedan `Up`.
  - Puertos en el host: 5173 (frontend), 8010 (backend) y 8025 (Mailpit). Postgres y Redis no se exponen.
- `docker compose logs backend worker beat frontend`: 0 tracebacks.
  - Beat: `beat: Starting...`.
  - Worker: `celery@… ready` con `core.run_automation` registrada.
  - Migraciones aplicadas limpias sobre la BD vacía y `System check identified no issues`.
- `make reset` también funciona de punta a punta: `down -v` → migrate → `seed_demo --reset` → `up -d --build`.

### 2. `make seed` dos veces seguidas

Exit 0 en ambas corridas, con los mismos conteos: 2 organizaciones, 3 propiedades, 8 usuarios, 7 memberships y
14 roles. El seed es idempotente.

### 3. Suites

| Suite | Resultado final | Al empezar A3 |
|---|---|---|
| `pytest -q` (TEST_DB_NAME=test_a3) | **798 passed** | 740 passed |
| `ruff check .` · `ruff format --check .` | limpio · 245 archivos formateados | limpio |
| `manage.py check` · `makemigrations --check` | sin problemas · "No changes detected" | igual |
| `manage.py spectacular --validate --fail-on-warn` | OK (sin warnings) | — |
| Frontend en contenedor (Node 24.15): `typecheck`, `lint`, `test`, `build` | verdes: **24 archivos, 178 tests**, sin stderr; build sin warning de chunks | 176 tests, con un warning `act(...)` en stderr |

El build del frontend se corrió con `--outDir /tmp/dist-check`, para no escribir archivos como root en el bind
mount.

### 4. Flujo real por el proxy de Vite

Lo corrí con curl, cookie jar y CSRF contra `http://localhost:5173/api/...`. El script está al final.

| Paso | Resultado |
|---|---|
| `GET /api/v1/accounts/auth/csrf/` | 200 y cookie `csrftoken` |
| `POST auth/login/` sin token | 403 `csrf_failed` |
| `POST auth/login/` con `Origin: http://evil.example` | 403 `csrf_failed` (Origin no confiable) |
| `POST auth/login/` con token y Origin propio (`OWNER@…`, sin distinguir mayúsculas) | 200 con `Me`; el token CSRF rota |
| `PATCH me/` con el token viejo / con el token nuevo | 403 / 200 |
| `GET me/` | 200, con `phone` |
| **`GET /api/v1/core/context/` + `X-Property-Id` (Casa Aurora, owner)** | **200** `{property, organization, role:"owner", permissions:["*"]}` |
| mismo endpoint sin encabezado | 400 `property_required` |
| owner de Grupo Andino pidiendo Casa Aurora | 404 `not_found` |
| `recepcion@casaaurora.co` | 200, rol `front_desk` con 26 permisos |
| `limpieza@grupoandino.co` (restringida a Medellín): Medellín / Bogotá | 200 / 404 |
| anónimo | 401 `not_authenticated` |
| `POST auth/logout/` → `GET me/` | 204 → 401 |

Otros endpoints por el proxy:
- `GET /api/v1/public/core/health/`: 200 `{"status":"ok"}`.
- `/api/docs/` y `/api/schema/`: 200.
- Rutas SPA (`/`, `/login`, `/app`, `/app/settings/rooms`, `/admin`, `/h/…`, `/sim/pay/…`, `/embed/…`): 200 con
  `index.html`.

Navegador (Chrome DevTools, contexto aislado):
- `/app/settings` anónimo redirige a `/login?next=…`.
- Login de recepción vuelve a `next`. Configuración muestra solo lo que permite `front_desk` (Categorías,
  Habitaciones, Portal del huésped).
- En "Mi perfil": guardo el teléfono, recargo, lo veo, cambio el nombre y guardo. En la BD quedan el nombre nuevo
  y el teléfono intacto.
- Consola sin errores ni warnings después del login.

### 5. Coherencia de contratos

Extraje del spec §4.2 y del plan §C las 51 firmas: 38 del spec y 13 del plan. Las comparé contra el código de
dos formas: con `grep` (las 51 existen en su módulo) y con `inspect` (nombres, tipo de parámetro, keyword-only y
valores por defecto).
- **45 coinciden exactas.**
- **6 difieren a propósito porque manda el plan (Step 2 / §C)**, y todas son compatibles hacia atrás:
  - `post_charge` agrega `tax_exempt` y `business_date`.
  - `audit.record` tiene `target=None, summary=""` y agrega `organization`, `actor_label`.
  - `raise_alert` agrega `source`.
  - `resolve_alert` agrega `*, actor=None`.
  - `automation.run(code, property=None, *, params=None, triggered_by=None)`.
  - `permissions.has_perm(user, prop, code)`: el spec dice `property`, pero el código del plan usa `prop`. Las
    llamadas posicionales funcionan con ambos.
- Anotaciones de retorno: faltaban en 17 funciones y ahora coinciden todas (ver "Lo corregido").
- Dataclasses (`Quote`, `NightPrice`, `TaxLine`, `DayRate`, `StayRequest`, `ReservationRequest`, `Offer`,
  `AssignmentReport`, `GuestInput`, `ToolCall`, `LLMResult`, `RunResult`, `Automation`) y errores de dominio: los
  fija `test_contracts.py` y coinciden con el plan Step 5.
- Señales: las 13 del spec §4.1 existen en `apps/core/signals.py`.

### 6. Permisos, roles, nav y rutas

- Backend:
  - Los 18 `apps/<app>/permissions.py` declaran exactamente los 57 códigos de §D, en el mismo orden y con
    etiquetas ES/EN.
  - El registro auto-descubierto es igual a §D, sin extras ni faltantes.
  - `ROLE_TEMPLATES` es igual al bloque de §D, y los 7 roles de sistema en la BD de las dos organizaciones
    coinciden (nombre, permisos, `is_system`). Ningún patrón de rol queda sin código que lo satisfaga.
- Frontend:
  - Las 18 carpetas de §E tienen `routes.tsx`, `nav.ts` y `locales/{es,en}.json`.
  - Los 46 ítems de nav coinciden con la tabla del plan Step 6 (id, sección, path y permiso). Los 5 de admin
    tienen `platformAdmin` y `gettingStarted` no pide permiso.
  - Cada ítem apunta a una ruta de su feature, y sus etiquetas existen en ES y EN.
  - Los 31 códigos de permiso usados en nav son todos de §D.
  - Existen todas las rutas principales de §E y todas las del spec §7.1. `/login` vive en `app/routes.tsx`.

### 7. Chequeos adicionales

- Modelos contra el spec §4: los 39 modelos tienen todos sus campos. Los extras están justificados: los de
  `AbstractBaseUser`, `AutomationRun.triggered_by`, `Invitation.all_properties` y
  `Reservation.hold_expires_at`. `Stay` no tiene `period`, como pide el plan.
- En Postgres existen: la extensión `btree_gist`, las restricciones de exclusión `stay_no_room_overlap` y
  `stay_no_bed_overlap`, los índices únicos parciales `alert_open_unique`, `guest_document_unique` y
  `user_email_ci_unique`, y los checks y uniques del plan.
- Worker: encolé `core.run_automation('core.cleanup')` y quedó un `AutomationRun success` con su auditoría
  `source="automation"`. Beat genera `core.cleanup → core.run_automation('core.cleanup',)` a las 04:30.
- Email: `send_mail` desde el backend llega a Mailpit (API :8025). Borré el correo de prueba.

---

## Lo corregido

Cada corrección: causa raíz → arreglo → test visto en rojo y luego en verde.

1. **"Mi perfil" borraba el teléfono guardado.** Era un bug con pérdida de datos.
   - Causa: `PATCH /me/` acepta `phone`, pero `GET /me/` no lo devolvía. El diálogo lo mostraba vacío y, al
     guardar cualquier otro campo, enviaba `phone: ""`.
   - Arreglo:
     - `MeSerializer` incluye `phone`, el único campo agregado a la forma del spec.
     - En el frontend, `Me.phone: string` y `makeMe()` con `phone`.
   - Tests:
     - `accounts/tests/test_auth.py`: forma de `Me` con `phone` y respuesta del `PATCH`.
     - `frontend/src/app/__tests__/ProfileDialog.test.tsx`: muestra el teléfono guardado y lo conserva al guardar
       otro campo. Con prueba de mutación: el test falla si el diálogo ignora `me.phone`.
   - Verificado también en el navegador.
2. **No existía ningún endpoint con alcance de propiedad**, y el checklist lo exige.
   - Arreglo: `GET /api/v1/core/context/` (`PropertyContextView` sobre `PropertyScopedAPIView`), documentado en
     OpenAPI con el encabezado `X-Property-Id`.
   - Para no duplicar formas, `Me` y el contexto usan los mismos helpers de `accounts/api/serializers.py`.
   - Test: `core/tests/test_context_api.py`, 10 casos: forma, 400, 401, 404 ×3, membership restringida, 402, 405 y
     esquema.
3. **Faltaban anotaciones de retorno en 17 contratos**: `availability`, `search_offers`, las 8 de
   `reservations.*`, `post_room_charges`, `refund_payment`, `create_payment_intent`, `sync_payment_intent`,
   `provision_room_type`, `integrations.get_setting` y `tokens.read_reservation_token`.
   - Arreglo: las anotaciones del spec y del plan. Donde había riesgo de import circular usé
     `from __future__ import annotations` con `TYPE_CHECKING`.
   - Test: `RETURNS` y `test_contract_return_type` en `core/tests/test_contracts.py`, con 44 casos.
4. **Cada 4xx/5xx de Django se imprimía dos veces.**
   - Causa: el logger `django` conservaba el handler de consola por defecto de Django, y además propagaba al
     handler de la raíz.
   - Arreglo: `LOGGING["loggers"]["django"]` usa nuestro handler, con `propagate: False`. Ahora cada registro sale
     una vez y con el mismo formato, incluido el access log de `runserver`.
   - Test: `core/tests/test_logging.py`.
5. **El worker de Celery advertía en cada arranque "running with superuser privileges"**, y era falso.
   - Causa: el contenedor corre como uid/gid 1000 sin entrada en `/etc/passwd`/`/etc/group`. Celery no resolvía
     el grupo y "asumía root".
   - Arreglo:
     - `backend/Dockerfile` crea el usuario y el grupo con `APP_UID`/`APP_GID`, sin tocar ids que ya existan.
     - `docker-compose.yml` los pasa como build args desde `HOST_UID`/`HOST_GID`.
   - Verificado: tras reconstruir, el log del worker ya no muestra `SecurityWarning`.
6. **Warning `act(...)` en `feedback.test.tsx`**, solo en el contenedor.
   - Causa: el cambio de idioma se hacía fuera de `act`.
   - Arreglo: `await act(() => i18n.changeLanguage('en'))`. Verificado sin stderr en el contenedor.
7. **Chrome reportaba "form field without id or name" en "Mi perfil".**
   - Causa: el `<select>` nativo oculto del `Select` de idioma no tenía nombre.
   - Arreglo: `name={field.name}`.
   - Test: en `ProfileDialog.test.tsx`, todos los controles del formulario tienen nombre. Verificado en el
     navegador: 0 controles sin nombre y consola limpia.

Documentación:
- `README.md` tiene ahora la estructura del frontend y menciona el endpoint de contexto.
- En `A1-backend-foundation.md`: el ejemplo de `Me` lleva `phone` y la tabla de API incluye `core/context`.
- En `A2-frontend-foundation.md`: la sugerencia del teléfono queda marcada como hecha.

Archivos tocados en A3:
- Backend:
  - `backend/apps/core/{api/views.py, urls.py, integrations.py, tokens.py}`
  - `backend/apps/core/tests/{test_context_api.py, test_logging.py, test_contracts.py}`
  - `backend/apps/accounts/api/serializers.py`, `backend/apps/accounts/tests/test_auth.py`
  - `backend/apps/bookings/services/{availability.py, reservations.py, charges.py}`
  - `backend/apps/finance/services.py`, `backend/apps/inventory/services.py`
  - `backend/config/settings.py`, `backend/Dockerfile`, `docker-compose.yml`
- Frontend:
  - `frontend/src/lib/auth.tsx`, `frontend/src/test/fixtures.ts`
  - `frontend/src/app/shell/ProfileDialog.tsx`, `frontend/src/app/__tests__/ProfileDialog.test.tsx`
  - `frontend/src/components/__tests__/feedback.test.tsx`
- Documentación: `README.md` y las notas A1, A2 y A3.

---

## Lo pendiente o para tener en cuenta

Nada bloquea la Fase B. Queda lo siguiente:

- **Stubs por diseño** (plan Step 5) con `NotImplementedError`, que completan B1, B2a, B2b, B3 y B4:
  `search_offers`, `reservations.*`, `post_room_charges`, `provision_rates`, `provision_room_type`,
  `void_charge`, `refund_payment`, `create_payment_intent`, `sync_payment_intent`, `find_duplicates` y
  `merge_guests`. `send_message` y `get_llm` siguen simulados hasta C6 y C9.
- **`/api/docs/` carga Swagger UI desde el CDN de jsDelivr** (`swagger-ui-dist@latest`). Sin internet la página
  queda en blanco, pero `/api/schema/` funciona. Para dejarlo 100 % offline hace falta `drf-spectacular-sidecar`
  (una dependencia nueva). Queda para D1.
- **En `/login` como anónimo, Chrome registra `Failed to load resource: 401`** para `GET /accounts/me/`.
  - Es la comprobación de sesión y es lo esperado: A1 fijó el 401 para anónimos. No es un error de JavaScript, y
    la Fase E no debería contarlo como fallo.
  - Si hubiera que eliminarlo, habría que cambiar el contrato (por ejemplo, un endpoint de sesión que responda
    200 a anónimos). No lo hice.
- **Este host no tiene el plugin buildx**: Compose avisa `requires buildx plugin` y usa el builder clásico. Es del
  entorno, no del repo.
- **Heredado de A1**: con `DEBUG=1`, `/media/` se sirve sin autenticación, incluidos los documentos de huéspedes.
  B3 y C5 deberían servirlos por una vista autenticada.
- `make test-front` y `make lint-front` usan `docker compose run` sin `--no-deps`, así que también levantan el
  backend. Es inofensivo.

---

## Cómo repetir la verificación

```bash
cd /home/breyner/Documents/new_project
docker compose down -v && docker compose up -d --build && docker compose ps
make seed && make seed
docker compose run --rm -e TEST_DB_NAME=test_a3 backend sh -c "pytest -q && ruff check . && ruff format --check . \
  && python manage.py check && python manage.py makemigrations --check --dry-run"
docker compose run --rm --no-deps frontend sh -c "npm run typecheck && npm run lint && npm run test \
  && npm run build -- --outDir /tmp/dist-check --emptyOutDir"
docker compose logs --no-color backend worker beat frontend | grep -ci traceback     # 0
```

Flujo por el proxy con cookie jar y CSRF:

```bash
B=http://localhost:5173; J=/tmp/jar
curl -s -o /dev/null -c $J -b $J $B/api/v1/accounts/auth/csrf/
T=$(awk '$6=="csrftoken"{print $7}' $J)
curl -s -c $J -b $J -H 'Content-Type: application/json' -H "Origin: $B" -H "X-CSRFToken: $T" \
  -X POST $B/api/v1/accounts/auth/login/ -d '{"email":"owner@casaaurora.co","password":"housetel123"}' > /tmp/me.json
P=$(python3 -c "import json; print(json.load(open('/tmp/me.json'))['memberships'][0]['properties'][0]['id'])")
curl -s -b $J $B/api/v1/accounts/me/
curl -s -b $J -H "X-Property-Id: $P" $B/api/v1/core/context/      # 200 {property, organization, role, permissions}
```
