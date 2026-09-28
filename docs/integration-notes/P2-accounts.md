# P2 — Cuentas: contraseña y verificación de email — integration notes

Estado (2026-09-28, modo MVP: sin escribir ni correr tests): **completo**. Olvidé mi contraseña, restablecer, cambiar
contraseña, verificación de email (modelo, migraciones, receiver, endpoints, `Me.email_verified`) y el frontend
(páginas públicas, "Mi cuenta y seguridad", chip de la topbar y enlace en el login). Verificado por curl a través del
proxy de Vite (70 requests y 33 comprobaciones, todas bien), con los correos reales en Mailpit, y visualmente en un Chrome headless
propio a 1440 y 375 px, en claro y oscuro (nunca el navegador compartido).

Esta pasada retomó un intento interrumpido que ya tenía casi todo el código. Lo revisé completo y agregué:
- textos más precisos sobre para qué sirve verificar;
- mensajes de validación en el idioma de la pantalla;
- la página de cuenta para el super-admin (`/admin/account`);
- en el admin de Django, un filtro "correo verificado" y que cambiar el correo lo marque sin verificar;
- esta nota.

Owner paths: `backend/apps/accounts/**`, `frontend/src/features/team/**`, `frontend/src/app/pages/LoginPage.tsx`
(solo el enlace) y esta nota. No toqué nada fuera de ahí. Sin dependencias nuevas.

Lectura rápida para otras tareas:

- **Correos reales**: los 3 correos de cuenta salen por el SMTP configurado (`EMAIL_*`, `DEFAULT_FROM_EMAIL`), no hay
  modo simulado. En desarrollo llegan a Mailpit (http://localhost:8025). Los enlaces usan `settings.FRONTEND_URL`: en
  producción debe ser la URL pública de la app (P1 ya la exige).
- **`Me`** suma `email_verified` (bool) y `email_verified_at` (ISO o `null`). Los usuarios que existían antes (la
  data migration), los del seed, los superusuarios y los que entran por invitación están verificados. Solo quedan sin
  verificar los que se registran (`/signup`) o se crean a mano en el admin, hasta que abren el enlace.
- **No verificar no bloquea nada**: es un recordatorio (chip en la topbar y tarjeta en "Mi cuenta"). Olvidé mi
  contraseña también funciona sin verificar, y abrir el enlace de restablecer verifica el correo.

---

## API implementada

Errores con la forma de siempre `{detail, code, fields?}`. `detail` en español, salvo los mensajes de los validadores
de contraseña de Django, que salen en el idioma de la pantalla (ver "Idioma"). Todos los POST exigen CSRF: los
públicos lo verifican a mano, como el login (`GET /api/v1/accounts/auth/csrf/` primero). Throttles en "Seguridad".

### Públicos (`/api/v1/public/accounts/`, sin sesión)

| Método y path | Body | Respuesta |
|---|---|---|
| `POST password/forgot/` | `{email}` | **Siempre 200** `{"detail": "Si el correo corresponde a una cuenta de Housetel, te enviamos un enlace para restablecer la contraseña."}`, exista o no la cuenta (sin enumeración). Solo si hay un usuario **activo** con ese correo (sin distinguir mayúsculas) sale el correo. Un email mal formado da 400 `validation_error`. Sin CSRF, 403 |
| `POST password/reset/check/` | `{uid, token}` | 200 `{"email": "v•••@casaaurora.co"}` si el enlace sirve (no cambia nada; la página lo pregunta antes de pedir la clave). 400 `invalid_token` si no |
| `POST password/reset/` | `{uid, token, new_password}` | 200 **`Me`**: guarda la clave e **inicia sesión** en este navegador (cookie de sesión nueva). Las demás sesiones del usuario mueren (cambia el hash de sesión). Verifica el correo si no lo estaba. Audita `accounts.password_reset`. 400 `invalid_token` (usado, vencido, alterado o usuario inactivo) · 400 `validation_error` con `fields.new_password: [...]` (validadores de Django) |
| `POST verify-email/` | `{token}` | 200 `{"email": "…", "email_verified": true, "already_verified": false}`; abrir otra vez el mismo enlace → `already_verified: true` (no es error). 400 `token_expired` (más de 7 días) · 400 `invalid_token` (firma mala, usuario inactivo o el correo cambió). No necesita sesión: sirve en el celular donde se abrió el correo. Audita `accounts.email_verified` |

### Staff (`/api/v1/accounts/`, sesión + CSRF; no requieren `X-Property-Id` y responden también con la organización suspendida)

| Método y path | Body | Respuesta |
|---|---|---|
| `POST me/password/` | `{current_password, new_password}` | 200 `{"detail": "Contraseña actualizada. Cerramos la sesión en tus otros dispositivos."}`. **Esta sesión sigue viva** (`update_session_auth_hash`) y las demás mueren. Correo de aviso "Tu contraseña de Housetel cambió". Audita `accounts.password_changed`. 400 `wrong_password` (`fields.current_password`) · 400 `same_password` (`fields.new_password`) · 400 `validation_error` (`fields.new_password`) |
| `POST me/verify-email/resend/` | — | 200 `{"sent": true, "email": "…", "email_verified": false}` con un enlace nuevo en el correo. Si ya estaba verificado: `{"sent": false, "email_verified": true}` (no envía nada). 503 `email_unavailable` si el SMTP falla |
| `GET me/` (A1, ampliado) | — | `Me` con los 2 campos nuevos |

```jsonc
// GET /api/v1/accounts/me/
{"id": "0472248c-…", "email": "owner@casaaurora.co", "full_name": "Valentina Rojas", "language": "es", "phone": "",
 "is_platform_admin": false,
 "email_verified": true, "email_verified_at": "2026-09-28T07:11:38.807976-05:00",   // nuevos (P2)
 "memberships": [ /* igual que antes */ ]}

// 400 de validadores (idioma de la pantalla)
{"detail": "Esta contraseña es demasiado común.", "code": "validation_error",
 "fields": {"new_password": ["Esta contraseña es demasiado común.", "Esta contraseña es completamente numérica."]}}

// 400 de contraseña actual incorrecta
{"detail": "La contraseña actual no es correcta", "code": "wrong_password",
 "fields": {"current_password": ["La contraseña actual no es correcta"]}}

// 429 (throttle, mensaje de DRF en el idioma del usuario)
{"detail": "Solicitud fue regulada (throttled). Se espera que esté disponible en 3080 segundos.", "code": "throttled"}
```

Enlaces de los correos:
- Restablecer: `${FRONTEND_URL}/reset-password/<uidb64>/<token>`. Usa `default_token_generator` de Django
  (`PasswordResetTokenGenerator`). El enlace muere al cambiar la clave o cuando el usuario **inicia sesión** (Django
  mete `last_login` en el token), y vence a los `PASSWORD_RESET_TIMEOUT` (default de Django: 3 días; el texto del
  correo se ajusta solo).
- Verificar: `${FRONTEND_URL}/verify-email/<token>`. Es `django.core.signing` con salt `accounts.verify-email` y vence
  a los 7 días. Lleva el id del usuario y un hash del correo (no el correo en claro), así que deja de servir si el
  correo cambia.
- "No fui yo" del aviso de cambio: `${FRONTEND_URL}/forgot-password?email=<correo>`.

### Correos (`apps/accounts/emails.py` + plantilla `accounts/email/account.html`)

Salen de Housetel, no del hotel, en el idioma del perfil (`User.language`, es|en). Van en HTML con el layout de
Housetel (terracota, botón y enlace de respaldo) y una alternativa de texto plano. Si el SMTP falla, se registra en
el log y **nunca rompe el flujo**: el signup o el cambio de clave siguen; `resend/` responde 503.

| Correo | Asunto ES / EN | Cuándo |
|---|---|---|
| Restablecer | "Restablece tu contraseña de Housetel" / "Reset your Housetel password" | `password/forgot/` con cuenta activa (máx. 1 por minuto y 5 por hora por dirección) |
| Verificar | "Confirma tu correo en Housetel" / "Confirm your email on Housetel" | Al crear un usuario (receiver), en `resend/` y al cambiar el correo en el admin |
| Aviso de cambio | "Tu contraseña de Housetel cambió" / "Your Housetel password changed" | Tras `me/password/` (con fecha y hora de Colombia y "No fui yo: restablecer la contraseña") |

## Contratos implementados / consumidos

No hay contratos nuevos entre apps. Servicios de la app, usables por otras tareas:

```python
# apps/accounts/passwords.py
request_password_reset(email) -> bool              # True si salió un correo (la API nunca lo dice)
check_reset_link(uidb64, token) -> User            # InvalidToken (400 invalid_token)
reset_password(uidb64, token, new_password, *, language=None) -> User
change_password(user, *, current_password, new_password, language=None) -> User
validate_new_password(user, password, *, field="new_password", language=None)   # DomainError validation_error
password_reset_url(user) -> str · forgot_password_url(email="") -> str · mask_email(email) -> str

# apps/accounts/verification.py
make_verification_token(user) -> str · verification_url(user) -> str
send_verification(user) -> bool                    # envía ya; False si el SMTP falló
send_verification_on_commit(user) -> None          # al confirmar la transacción, si sigue pendiente y activo
verify_email(token) -> tuple[User, bool]           # (user, verificado_ahora); TokenExpired / InvalidToken

# apps/accounts/models.py
User.email_verified_at: DateTimeField(null)        # + propiedad User.email_verified
```

Cambios de comportamiento en lo existente:
- `UserManager.create_user` crea verificados a los usuarios mientras `is_seeding()`. `create_superuser` siempre
  crea verificado.
- `team.accept_invitation`: el usuario nuevo nace verificado (la invitación llegó a ese correo) y el existente queda
  verificado al aceptar.

Consumidos: `core.audit.record`, `core.signals.is_seeding`, `core.api.authentication.enforce_csrf`,
`core.errors.DomainError`.

## Señales emitidas / escuchadas

- Escuchada: `post_save` de `User` con `created` → `receivers.email_verification_link` → `send_verification_on_commit`.
  - Hace `if is_seeding(): return`.
  - Ignora cargas `raw` (fixtures) y usuarios que ya nacen verificados (invitación, superusuario, seed).
  - El correo sale en `transaction.on_commit` (robusto): un signup que falla no envía nada.
- Emitidas: ninguna.

## Automatizaciones registradas

Ninguna.

## Proveedores de integración registrados

Ninguno: el correo usa el `EMAIL_BACKEND` de Django (SMTP), igual que las invitaciones.

## Extensiones de frontend exportadas (widgets, tabs, topbar, commands)

Rutas (`features/team/routes.tsx`, lazy):

| Ruta | Página | Notas |
|---|---|---|
| `/forgot-password` (pública) | `ForgotPasswordPage` | `?email=` la precarga (el login y "Mi cuenta" la pasan). Después muestra "Revisa tu correo", con "Enviar de nuevo" (espera de 60 s) y "Usar otro correo" |
| `/reset-password/:uid/:resetToken` (pública) | `ResetPasswordPage` | Primero revisa el enlace (`reset/check/`). Si no sirve, muestra "Este enlace ya no sirve" con "Pedir un enlace nuevo". Si sirve, pide la clave nueva con una lista de reglas en vivo y "Guardar y entrar" → aterriza con `homeFor(me)` |
| `/verify-email/:verifyToken` (pública) | `VerifyEmailPage` | Confirma al cargar (una sola llamada, aunque se vuelva a montar). Estados: listo, ya estaba verificado, vencido (reenviar si hay sesión; si no, "Inicia sesión para pedir otro") y no válido. Si hay sesión en ese navegador, refresca `Me` |
| `/app/settings/account` | `AccountPage` "Mi cuenta y seguridad" | Tarjeta **Correo**: estado Verificado/Sin verificar, fecha y "Reenviar enlace". Tarjeta **Contraseña**: actual, nueva y repetir, con reglas en vivo. Los errores del servidor salen bajo su campo |
| `/admin/account` (**nuevo**, super-admin) | la misma `AccountPage` | El super-admin no tiene hotel: en `/app` vería "sin propiedades" |

Los parámetros no se llaman `token` a propósito: `PublicLayout` le pasa `params.token` al widget de chat como token
de portal, y estos secretos no deben viajar a otro endpoint.

Nav (`features/team/nav.ts`):
- `account` → sección `settings`, orden 5, **sin permiso**: todos los roles ven ahora "Configuración", aunque sea
  solo con este ítem.
- `adminAccount` → sección `admin`, `platformAdmin: true`, orden 90.

Topbar (`features/team/topbar.tsx`): `VerifyEmailChip` (`id: team-verify-email`, `order: 4`).
- Solo se dibuja si `Me.email_verified === false`.
- Chip ámbar "Verifica tu correo"; en el celular, solo el ícono.
- Abre un popover con el correo, "Reenviar enlace" y "Mi cuenta".

LoginPage: enlace "¿Olvidaste tu contraseña?" bajo la contraseña. Lleva el correo escrito en `?email=`.

Reutilizables de la feature:
- Componentes: `PasswordInput` (con mostrar u ocultar), `PasswordRules` (lista de reglas en vivo accesible),
  `ResendVerificationButton` (con la espera de 60 s compartida entre copias, en `sessionStorage`) y la escena de
  llaves (`KeyCard`, `KeySleeve`, `RecodeScene`, `Stamp`).
- En `account-api.ts`: los hooks `useForgotPassword`, `useResetLink`, `useResetPassword`, `useVerifyEmail`,
  `useChangePassword` y `useResendVerification`, y las funciones `isEmailUnverified(me)` y `emailVerifiedAt(me)`.

i18n: `team` ES/EN con paridad exacta (221 claves). Los textos de los correos viven en el backend (dict ES/EN en
`emails.py`).

## Dependencias nuevas (pip/npm) y por qué

Ninguna.

## Cambios requeridos en archivos compartidos u otras apps (para P-INT)

1. **`config/settings.py` (P1), recomendado.** `UserAttributeSimilarityValidator` usa por defecto `username`,
   `first_name`, `last_name` y `email`. Nuestro `User` solo tiene `email` y `full_name`, así que hoy **no compara con
   el nombre**: "ana prueba" pasa para Ana Prueba. Basta con:
   `{"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator", "OPTIONS": {"user_attributes": ("email", "full_name")}}`.
   Aplica también al signup y a las invitaciones.
2. **`frontend/src/app/layouts/PublicLayout.tsx` (P1), recomendado.** Pasar `portalToken` al widget de chat solo en
   las rutas del portal (`/g/:token`). Hoy `/invite/:token` (B3) también se llama `token`, y el widget manda el secreto
   de la invitación a `GET /api/v1/public/ai/portal-chat/<token>/` (responde 404, pero el secreto queda en otro log).
   Las rutas nuevas de P2 ya evitan el nombre.
3. **`frontend/src/app/shell/UserMenu.tsx` (P1), opcional.** Ítem "Mi cuenta y seguridad" → `/app/settings/account`
   (o `/admin/account` en el área admin). Hoy se llega por Configuración. La etiqueta existe: `team:nav.account`.
4. **`frontend/src/lib/auth.tsx` (P1), opcional.** `Me` ya tiene `email_verified?`. Falta `email_verified_at?: string
   | null`; mientras tanto `account-api.ts` usa `AccountMe`.
5. **`make smoke` (P-INT).** Pasos de P2 para `backend/scripts/smoke_proxy.py`, con sus helpers `call()`,
   `call_status()` y `check()`, dentro de la sesión del dueño:
   ```python
   # P2: olvidé mi contraseña (200 exista o no la cuenta), Me.email_verified y enlace de verificación alterado
   same = call("POST", "/api/v1/public/accounts/password/forgot/", {"email": "nadie-smoke@example.com"})
   check("detail" in same, "forgot always answers 200")
   me = call("GET", "/api/v1/accounts/me/")
   check("email_verified" in me, "Me carries email_verified")
   status, sent = call_status("POST", "/api/v1/accounts/me/verify-email/resend/")  # demo user: sent=False
   check(sent["email_verified"] is True, "demo users are verified")
   bad = call("POST", "/api/v1/public/accounts/verify-email/", {"token": "x"}, expect=(400,))
   check(bad["code"] == "invalid_token", "tampered verification link is rejected")
   ```
   El recorrido completo que corrí (enlaces reales, sesiones que mueren, reuso y throttle) está paso a paso en
   "Verificación". Para automatizarlo, los enlaces se leen con la API de Mailpit: `GET :8025/api/v1/messages` y
   `GET :8025/api/v1/message/<id>`, campo `Text`.
6. **`docs/integraciones-reales.md` (P1).** En la sección SMTP, mencionar que los correos de cuenta (restablecer,
   verificar, aviso de cambio) salen de `DEFAULT_FROM_EMAIL` con enlaces a `FRONTEND_URL`: los dos tienen que ser los
   reales para que el piloto recupere contraseñas.
7. **Tests viejos que esta tarea rompe** (no los toqué, modo MVP):
   - `backend/apps/accounts/tests/test_auth.py`: compara `Me` exacto y le faltan `email_verified` y
     `email_verified_at`.
   - `frontend/src/app/__tests__/extensions.test.ts`: la lista `EXPECTED_NAV` no tiene
     `['team', 'account', 'settings', '/app/settings/account', undefined]` ni
     `['team', 'adminAccount', 'admin', '/admin/account', undefined, true]`.

## Seed

Sin cambios en `apps/accounts/seed.py` (B3).
- Los usuarios demo nacen verificados: `create_user` bajo `is_seeding()`.
- Los que ya estaban en la BD quedaron verificados con la data migration `0004`.
- El seed no envía correos.

Probado en una transacción revertida (1,2 s): `seed_base` recreó un usuario demo verificado y sin correos programados;
el seed de accounts dejó 2 roles "Recepción nocturna" y 0 usuarios demo sin verificar. En la misma transacción:
- un usuario normal programa 1 correo;
- aceptar una invitación crea al usuario verificado y con 0 correos;
- un usuario existente que acepta queda verificado.

Todo se revirtió.

Para ver el chip en la demo no hace falta seed: un hotel creado con `/signup` queda sin verificar.

## Seguridad (decisiones)

- **Sin enumeración.** `forgot/` responde igual con y sin cuenta, y los errores del enlace de restablecer son siempre
  `invalid_token`, sin decir por qué. El formulario de signup, en cambio, sí dice "Ya existe una cuenta con este
  email" (decisión previa de C11).
- **Throttles** (`apps/accounts/throttles.py`). Usan `ScopedRateThrottle` con defaults propios y se pueden
  sobrescribir en `REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"][<scope>]`. En desarrollo son más amplios, porque todos
  los navegadores llegan por el proxy de Vite con la misma IP.

  | Scope | Producción | Desarrollo | Por |
  |---|---|---|---|
  | `password_forgot` | 10/hora | 60/hora | IP |
  | `password_reset` (`reset/` y `reset/check/`) | 30/hora | 120/hora | IP |
  | `email_verify` | 30/hora | 120/hora | IP |
  | `password_change` | 10/hora | 30/hora | usuario (adivinar la clave actual desde una sesión abierta) |
  | `email_verify_resend` | 5/hora | 20/hora | usuario |

  Además, por dirección (Redis), máximo 1 correo de restablecer por minuto y 5 por hora, aunque vengan de muchas IP.
  Detrás de nginx necesita `NUM_PROXIES` (P1).
- **Sesiones.** Restablecer cierra todas las sesiones y abre una nueva en este navegador. Cambiar la clave conserva la
  actual y cierra las demás. Probado con 4 sesiones paralelas.
- **Invitaciones.** La invitación prueba el correo: aceptar marca verificado y nunca manda correo de verificación.
- **Admin de Django.** Columna y filtro "correo verificado". Si se cambia el correo de un usuario, queda sin verificar
  y le llega un enlace a la dirección nueva, salvo que el admin también edite `email_verified_at`.
- **Idioma.** Los validadores de Django responden en el idioma de la pantalla, el `Accept-Language` que manda la SPA
  (LocaleMiddleware de P1). Con sesión manda el idioma del perfil (el de UserLanguageMiddleware). Sin cabecera se usa
  el idioma del perfil. Los correos siempre van en el idioma del perfil.

## Verificación (mínima del modo MVP)

- `manage.py check` sin problemas. `makemigrations accounts --check --dry-run` → "No changes detected". Migraciones
  `0003_user_email_verified_at` y `0004_mark_existing_users_verified` aplicadas en la BD de desarrollo.
- `ruff check` y `ruff format --check` limpios en `apps/accounts`.
- `spectacular --validate`: los 7 endpoints de P2 (y `Me`) con esquemas propios (`PasswordChangeRequest`,
  `AccountMessage`, `VerificationResend`, `PasswordForgotRequest`, `PasswordResetRequest`, `PasswordResetLink(Info)`,
  `VerifyEmailRequest/Result`). Ningún warning es de accounts; los 2 que quedan son de `imports`, P5.
- Frontend:
  - `npx tsc -p tsconfig.app.json --noEmit | grep -E "features/team|pages/LoginPage"`: sin errores. Los únicos
    errores del proyecto están en `frontdesk/__tests__/wizard.test.ts` (P3).
  - `npx eslint src/features/team src/app/pages/LoginPage.tsx`: limpio.
- **Curl por el proxy de Vite (http://localhost:5173)**, con cookie jar + CSRF, sobre 2 usuarios de prueba (es y en)
  y los correos leídos de Mailpit. 70 requests y 33 comprobaciones, todas bien:
  - Verificación:
    - el receiver manda el correo ES/EN al crear el usuario;
    - `Me.email_verified=false`;
    - `resend` envía otro;
    - un token alterado da 400 `invalid_token`;
    - verificar da `already_verified=false` la primera vez y `true` la segunda, y `Me` pasa a `true`;
    - `resend` ya verificado da `sent=false`, y sin sesión da 401.
  - Olvidé:
    - misma respuesta 200 para un correo desconocido y uno conocido (en mayúsculas);
    - email inválido da 400 y sin CSRF da 403;
    - llega exactamente 1 correo con el enlace `/reset-password/<uid>/<token>`, y un segundo pedido antes de 60 s no
      manda nada.
  - Restablecer:
    - `check` devuelve `p•••@example.com` y un token malo da 400;
    - `12345678` da 400 con "demasiado común" y "completamente numérica";
    - la clave buena da `Me` y deja sesión en ese navegador;
    - las otras 2 sesiones pasan a 401;
    - reusar el enlace da 400;
    - la clave vieja ya no entra y la nueva sí.
  - Cambiar:
    - actual incorrecta da `wrong_password`, la misma clave da `same_password` y una común da `validation_error`;
    - la buena da 200: esta sesión sigue y la otra pasa a 401;
    - llega el aviso por correo.
  - Inglés: el usuario `en` recibe "Reset your Housetel password" y "This password is too common.". Con
    `Accept-Language: es` sale en español.
  - Throttle: `me/password/` da 429 al pasar las 30 por hora (desarrollo).
  - Tiempos: 5–60 ms, salvo los que calculan el hash de la clave (login, `reset/`, `me/password/`: ~150–480 ms).
- En shell: un token de 8 días da `token_expired` y uno de 6 días sirve. Tokens de otro salt, con payload de lista, con
  UUID inválido o con el correo cambiado dan `invalid_token`.
- El admin de Django lista y filtra `?email_verified=no|yes` (200).
- **Visual** (Chrome headless propio, perfil temporal, puerto 9571):
  - en esta pasada: el login con el enlace, el chip y su popover, "Mi cuenta" sin verificar y `/admin/account`, a
    1440 y 375 px y en oscuro;
  - la pasada anterior ya había revisado `/forgot-password`, `/reset-password/…` y `/verify-email/…` en todos sus
    estados, en claro, oscuro y 375 px.

  Sin desborde horizontal ni errores de consola. El único 401 es el `me/` anónimo del login, esperado.

Datos de prueba: borré los usuarios `p2-*@example.com` que creé, y sus correos en Mailpit. La BD de desarrollo queda
como estaba, salvo `email_verified_at` (la data migration marcó a todos como verificados).

## Limitaciones conocidas / pendientes

- **El envío es síncrono.** El SMTP corre dentro del request, como las invitaciones de B3. Un SMTP lento demora el
  signup y `forgot/`, y la diferencia de tiempo podría insinuar si una cuenta existe (el signup ya lo dice
  explícitamente). Lo siguiente sería una tarea de Celery `accounts.send_email`; no la hice porque exige reiniciar
  el worker compartido.
- El enlace de restablecer dura 3 días (default de Django). Si se quiere más corto, se ajusta
  `PASSWORD_RESET_TIMEOUT` en settings (P1); el correo lo refleja solo.
- No hay 2FA, ni lista de sesiones, ni "cerrar las demás sesiones" como botón aparte (cambiar la clave ya lo hace).
- No hay UI para cambiar el correo (el `PATCH /me/` de A1 no lo permite); solo el admin de Django.
- Verificar no restringe nada. Si más adelante se quiere exigir para acciones sensibles (invitar, cobros), el dato ya
  está en `Me`.
- Un usuario sin propiedades activas ve "sin propiedades" en `/app` y no llega a `/app/settings/account`. Puede
  recuperar su clave por `/forgot-password`. Los super-admins tienen `/admin/account`.

---

## Cómo probarlo en la UI

**Entorno:** app http://localhost:5173 · Mailpit http://localhost:8025 · clave demo `housetel123`.

> **Ojo con los usuarios demo.** Restablecer o cambiar la clave de un usuario demo la deja distinta de
> `housetel123`. Mejor pruébalo con un hotel creado con `/signup` o con `owner@hostaldemo.co`, y si usas otro vuelve a
> poner `housetel123` desde "Mi cuenta" (los validadores la aceptan para los usuarios de los hoteles). **No lo
> pruebes con `admin@housetel.co`:** ahí `housetel123` es "demasiado similar al email". Si hace falta restaurarlo:
> `docker compose exec -T backend python manage.py shell -c "from apps.accounts.models import User; u=User.objects.get(email='admin@housetel.co'); u.set_password('housetel123'); u.save()"`.

**1. Verificación de email (signup)** — anónimo, luego el dueño nuevo
1. `/signup` → crea un hotel con un correo nuevo (p. ej. `piloto.p2@example.com`). Aterrizas en
   `/app/getting-started`.
2. En la topbar aparece el chip ámbar **"Verifica tu correo"** (a 375 px, solo el ícono del sobre). Clic → popover
   "Confirma tu correo" con tu dirección, **Reenviar enlace** y **Mi cuenta**.
3. **Reenviar enlace** → toast "Te enviamos un enlace nuevo a …". El botón pasa a "Reenviar en 59 s"; la espera
   también se ve en "Mi cuenta".
4. En Mailpit hay 2 correos **"Confirma tu correo en Housetel"** (el del signup y el reenviado): layout Housetel con
   botón **Confirmar mi correo** y "vence en 7 días".
5. Abre el enlace → `/verify-email/<token>`: tarjeta de llave con el sello **VERIFICADO**, "Correo confirmado" e
   **Ir a Housetel**. Vuelve a la app: el chip ya no está. En `/app/settings/account` sale **Verificado** con la fecha.
6. Abre el mismo enlace otra vez → "… ya estaba verificado". Cambia una letra del token → sello **NO VÁLIDO**, "Este
   enlace no es válido".
7. En otro navegador o incógnito, sin sesión, el enlace también verifica ("Iniciar sesión").

**2. Olvidé mi contraseña** — con el usuario del paso 1 (o `owner@hostaldemo.co`)
1. Cierra sesión. En `/login` escribe el correo → **¿Olvidaste tu contraseña?**: `/forgot-password` llega con el
   correo ya escrito. A la izquierda, en escritorio, el sobre de la llave muestra lo que vas escribiendo.
2. **Enviar enlace** → "Revisa tu correo" (sello **ENVIADA**). La respuesta es igual para un correo que no existe;
   pruébalo con `nadie@example.com`. En desarrollo hay un aviso con el enlace a Mailpit.
3. "Enviar de nuevo" espera 60 s. "Usar otro correo" vuelve al formulario.
4. Mailpit → **"Restablece tu contraseña de Housetel"** → **Elegir contraseña nueva** →
   `/reset-password/<uid>/<token>`: "Para la cuenta p•••@example.com", con la escena de las llaves viejas
   **ANULADAS** y la **Llave nueva**.
5. Escribe `12345678` → las reglas en vivo (8 caracteres, no solo números, las dos coinciden) → al enviar, el error
   del servidor sale bajo el campo ("Esta contraseña es demasiado común. …").
6. Una clave buena en los dos campos → **Guardar y entrar** → toast "Contraseña actualizada…" y aterrizas en `/app`
   con sesión.
7. Si antes tenías otra sesión abierta con ese usuario (otro navegador o incógnito), su siguiente acción la manda al
   login.
8. Abre el mismo enlace otra vez → **"Este enlace ya no sirve"** con **Pedir un enlace nuevo**.
9. Detalle de Django: el enlace también muere si inicias sesión antes de usarlo.

**3. Cambiar contraseña** — `/app/settings/account` ("Configuración" → **Mi cuenta y seguridad**, primer ítem, visible
para todos los roles, incluida limpieza)
1. Tarjeta **Contraseña**: actual equivocada → "La contraseña actual no es correcta." bajo el campo. La misma que la
   actual → "La contraseña nueva debe ser distinta de la actual.".
2. Datos correctos → **Cambiar contraseña** → toast "Contraseña cambiada. Cerramos tu sesión en los demás
   dispositivos."; el formulario se limpia y **sigues conectado**. Otra sesión abierta de ese usuario cae al login.
3. En Mailpit: **"Tu contraseña de Housetel cambió"** con fecha y hora de Colombia, y el botón "No fui yo: restablecer
   la contraseña", que abre `/forgot-password?email=…`.
4. El enlace "¿Olvidaste tu contraseña actual?" del pie lleva a `/forgot-password` con tu correo.

**4. Invitaciones (verificadas sin correo extra)** — `owner@casaaurora.co`
- `/app/settings/users` → invita un correo nuevo → abre `/invite/<token>` desde Mailpit en incógnito → crea la cuenta.
  El usuario nuevo **no** ve el chip y Mailpit **no** recibe "Confirma tu correo".

**5. Super-admin** — `admin@housetel.co`
- `/admin` → ítem **Mi cuenta y seguridad** al final del menú → `/admin/account` con la misma página: correo verificado
  y cambio de contraseña. Mira la advertencia de arriba antes de cambiarla.

**6. Admin de Django** (desarrollo) — `/django-admin/accounts/user/`
- Columna "Correo verificado" y filtro "correo verificado: Sí/No". Si le cambias el correo a un usuario, queda sin
  verificar y le llega "Confirma tu correo" a la dirección nueva.

**7. Idioma, tema y móvil**
- Cambia a **inglés** en la topbar o en el login: todas las pantallas de P2 en inglés ("Forgot your password?", "My
  account & security", "Verify your email"…). Los errores de los validadores siguen el idioma de la pantalla. Los
  correos siguen el idioma del **perfil**: cámbialo en "Perfil" del menú de usuario y pide un enlace.
- Tema **oscuro**: las tarjetas de llave siguen opacas y legibles.
- **375 px**: `/forgot-password`, `/reset-password/…`, `/verify-email/…` y `/app/settings/account` sin scroll
  horizontal. En el celular, la escena de las llaves de las páginas públicas se oculta (repite el texto).
