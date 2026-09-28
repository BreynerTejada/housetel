# Despliegue de Housetel en producción

Guía para poner Housetel en un servidor propio para el piloto con hoteles reales. El stack de producción vive en
`docker-compose.prod.yml` y convive con el de desarrollo: usa otro proyecto de Compose (`housetel-prod`), otro
archivo de entorno (`.env.prod`) y otro puerto (`8080`).

Para conectar pagos, DIAN, TRA, WhatsApp y los canales de verdad, sigue después
[`docs/integraciones-reales.md`](integraciones-reales.md).

---

## 1. Arquitectura

```
Internet ──HTTPS──▶ TLS (Caddy · balanceador de la nube · Cloudflare)
                        │  X-Forwarded-Proto: https
                        ▼
                  nginx :8080  ── SPA compilada (index.html + /assets con hash, CSP, gzip)
                        │         /static/  (collectstatic: admin de Django, Swagger UI)
                        │         /media/photos|branding|booking-engine/  (fotos públicas)
                        │         /media/<cualquier otra cosa> → 404
                        ▼ /api/, /django-admin/
                  gunicorn (Django) ──▶ PostgreSQL 17 (volumen pgdata)
                        │              Redis 7 (volumen redisdata: caché, broker, throttles)
                  worker Celery ◀── beat Celery (20 automatizaciones)

Volúmenes: media (fotos públicas, nginx la lee), private_media (documentos de identidad, firmas, facturas,
reportes SIRE, fotos de daños: solo la montan backend y worker, nginx nunca), static, pgdata, redisdata.
```

| Servicio | Imagen | Qué hace | Healthcheck |
|---|---|---|---|
| `nginx` | `housetel-web:prod` (Node 24 compila la SPA → nginx 1.29) | Único puerto publicado (`HOUSETEL_HTTP_PORT`, 8080) | `GET /healthz` |
| `backend` | `housetel-backend:prod` (Python 3.13, usuario sin privilegios) | `migrate` + `collectstatic` al arrancar, luego gunicorn | `GET /api/v1/public/core/health/` |
| `worker` | la misma | Celery worker (PDF, correos, sincronizaciones) | `celery inspect ping` |
| `beat` | la misma | Programa las automatizaciones | — (se reinicia solo) |
| `db` | `postgres:17-alpine` | Base de datos | `pg_isready` |
| `redis` | `redis:7-alpine` (AOF) | Broker, caché y límites de peticiones | `redis-cli ping` |

Todos con `restart: unless-stopped` y logs de Docker rotados (5 × 20 MB por servicio).

### Qué cambia con `DJANGO_ENV=production`

| Tema | Desarrollo | Producción |
|---|---|---|
| Arranque | tolera todo | **no arranca** con `DJANGO_DEBUG=1`, sin `DJANGO_SECRET_KEY`, sin `FERNET_KEY` válida o sin `FRONTEND_URL` |
| Hosts / CSRF | `*` y `localhost:5173` | `DJANGO_ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS` (por defecto, el host y el origen de `FRONTEND_URL`) |
| HTTPS | — | `SECURE_PROXY_SSL_HEADER`, `SECURE_SSL_REDIRECT`, HSTS de 1 año con subdominios y preload, cookies de sesión y CSRF `Secure` |
| Cabeceras | nosniff, `Referrer-Policy: same-origin`, `X-Frame-Options: DENY` en la API | igual + CSP, `Permissions-Policy`, HSTS en nginx |
| Límite de login por IP | detrás del proxy de Vite | `NUM_PROXIES` (nginx = 1) para que DRF vea la IP real |
| Logs | texto | **JSON**, una línea por evento, con el `request_id` que también registra nginx |
| `/django-admin/` | abierto (con su login) | no existe salvo `ADMIN_ENABLED=1`, y aun así **404 para quien no sea staff con sesión** |
| `/api/schema/`, `/api/docs/` | públicos (Swagger por CDN o sidecar) | **solo staff** (`is_staff`); Swagger servido sin internet (`drf-spectacular-sidecar`) |
| Simulaciones | activas | **apagadas**: la pasarela simulada y los simuladores responden 404 y salen del menú; toda integración nueva arranca en modo real y deshabilitada hasta configurarla (`HOUSETEL_ALLOW_SIMULATIONS=1` las vuelve a encender en un servidor de demo) |
| Errores de la API | en el idioma del usuario o de `Accept-Language` | igual |

---

## 2. Requisitos

- Un servidor Linux con Docker 24+ y Docker Compose 2.24+ (el `env_file` usa `required:`). Para un piloto de 1–3
  hoteles bastan **2 vCPU y 4 GB de RAM** con 40 GB de disco; con PostgreSQL administrado, 2 GB alcanzan.
- Un dominio (p. ej. `app.tuempresa.co`) y TLS delante de nginx.
- Región con buena latencia a Colombia: Bogotá o São Paulo (AWS `sa-east-1`, GCP `southamerica-east1`) o Miami /
  `us-east-1`.
- Un proveedor de correo transaccional (SES, Postmark, SendGrid, Brevo…) con SPF y DKIM del dominio remitente.

---

## 3. Primer despliegue, paso a paso

1. **Clona el repositorio** en el servidor y entra a la carpeta.
2. **Crea el archivo de entorno** a partir de la plantilla y protégelo:
   ```bash
   cp deploy/env.prod.example .env.prod && chmod 600 .env.prod
   ```
   Completa como mínimo:

   | Variable | Qué poner |
   |---|---|
   | `FRONTEND_URL` | `https://app.tuempresa.co` (la URL pública; con ella se construyen los enlaces de correos, pagos y portal) |
   | `DJANGO_SECRET_KEY` | `python3 -c "import secrets; print(secrets.token_urlsafe(50))"` |
   | `FERNET_KEY` | `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` — guárdala también fuera del servidor: cifra las llaves de Wompi, Factus, WhatsApp… y sin ella no se pueden leer |
   | `POSTGRES_PASSWORD` | letras y números (va dentro de `DATABASE_URL`) |
   | `EMAIL_*`, `DEFAULT_FROM_EMAIL` | tu SMTP transaccional |
   | `SUPPORT_WHATSAPP`, `SUPPORT_EMAIL`, `SUPPORT_DOCS_URL` | los canales que verán los hoteles en "Ayuda y soporte" |
   | `NUM_PROXIES` | 1 si el TLS termina en nginx; **2** si hay un proxy (Caddy, balanceador, Cloudflare) delante de nginx |

   `.env.prod` tiene todos los secretos: **nunca lo subas a git**.
3. **Construye las imágenes**: `make prod-build` (~2–3 min la primera vez).
4. **Levanta el stack**: `make prod-up` (espera a que todos los servicios queden *healthy* y muestra `make prod-ps`).
   El backend aplica las migraciones y copia los estáticos en cada arranque.
5. **Crea el super-admin** de la plataforma: `make prod-createsuperuser` (pide email y contraseña; también puede
   promover a un usuario existente). Con él entras a `/admin` en la app.
6. **Pon TLS delante.** Ejemplo con Caddy en el mismo servidor (certificados automáticos de Let's Encrypt):
   ```caddyfile
   app.tuempresa.co {
       encode gzip
       reverse_proxy 127.0.0.1:8080
   }
   ```
   Caddy envía `X-Forwarded-Proto` y `X-Forwarded-For`: deja `NUM_PROXIES=2`. Con un balanceador de la nube, el
   mismo criterio (un proxy más). Si prefieres terminar TLS en nginx, agrega un `server` con `listen 443 ssl` en
   `deploy/nginx/templates/default.conf.template` y publica el 443.
7. **Verifica** (con tu dominio):
   ```bash
   curl -fsS https://app.tuempresa.co/api/v1/public/core/health/ready/   # {"status":"ok","checks":{...}}
   curl -s -o /dev/null -w "%{http_code}\n" https://app.tuempresa.co/api/docs/      # 401 (solo staff)
   curl -s -o /dev/null -w "%{http_code}\n" https://app.tuempresa.co/django-admin/  # 404
   curl -sI https://app.tuempresa.co/ | grep -i -E "strict-transport|content-security"
   ```
   y abre la app: login, sin "Entorno de demostración" arriba y sin simuladores en el menú.
8. **Primer hotel**: el propio hotel se registra en `/signup` (prueba de 14 días) o lo creas desde `/admin`.
   Luego, en *Configuración → Integraciones*, conecta sus proveedores reales
   ([`docs/integraciones-reales.md`](integraciones-reales.md)).

> **Cobro de la suscripción (saas_billing).** Sin las llaves `WOMPI_PLATFORM_*` (o con el cobro desactivado en
> `/admin/billing`), la integración de cobro de la plataforma no está en vivo y el ciclo diario
> (`saas.billing_cycle`) queda **omitido**: no cobra, no convierte pruebas vencidas ni marca mora o suspende a
> ninguna organización (P-INT). Para empezar a cobrar: define las llaves, reinicia `backend`, `worker` y `beat`, y
> activa el cobro en `/admin/billing` (`collection_available: true` en `GET /api/v1/saas/admin/billing-settings/`).
>
> **Factura electrónica y TRA sin configurar.** Mientras un hotel no conecte Factus o la TRA, sus salidas quedan en
> *Legal → Pendientes* y sus registros TRA *pendientes*: no se numera ni se envía nada hasta que la integración esté
> en vivo ([`docs/integraciones-reales.md`](integraciones-reales.md) §0.1).

---

## 4. Variables de entorno

La plantilla comentada completa es [`deploy/env.prod.example`](../deploy/env.prod.example). Resumen:

| Grupo | Variables |
|---|---|
| Obligatorias | `FRONTEND_URL`, `DJANGO_SECRET_KEY`, `FERNET_KEY`, `POSTGRES_PASSWORD` |
| Web y proxies | `HOUSETEL_HTTP_PORT` (8080), `DJANGO_ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `NUM_PROXIES`, `DJANGO_SECURE_SSL_REDIRECT` (1), `DJANGO_HSTS_SECONDS` (31536000), `NGINX_HSTS`, `PUBLIC_BASE_URL`, `GUNICORN_WORKERS`, `GUNICORN_THREADS`, `GUNICORN_TIMEOUT`, `CELERY_CONCURRENCY`, `NGINX_CLIENT_MAX_BODY_SIZE` (25m), `NGINX_CSP_IMG_SRC`, `NGINX_CSP_CONNECT_SRC` |
| Accesos de administración | `ADMIN_ENABLED` (0), `ADMIN_STAFF_ONLY` (1), `API_DOCS_PUBLIC` (0) |
| Simulaciones | `HOUSETEL_ALLOW_SIMULATIONS` (0 en producción) |
| Soporte | `SUPPORT_WHATSAPP`, `SUPPORT_EMAIL`, `SUPPORT_DOCS_URL` |
| Correo | `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS` / `EMAIL_USE_SSL`, `DEFAULT_FROM_EMAIL`, `SERVER_EMAIL` |
| IA | `GEMINI_API_KEY`, `GEMINI_MODEL`, `ANTHROPIC_API_KEY`, `CLAUDE_MODEL` |
| Cobro de la plataforma | `WOMPI_PLATFORM_ENV`, `WOMPI_PLATFORM_PUBLIC_KEY`, `WOMPI_PLATFORM_PRIVATE_KEY`, `WOMPI_PLATFORM_INTEGRITY_SECRET`, `WOMPI_PLATFORM_EVENTS_SECRET` |
| Monitoreo | `SENTRY_DSN`, `SENTRY_TRACES_SAMPLE_RATE` (0), `SENTRY_RELEASE`, `SENTRY_ENVIRONMENT`, `LOG_LEVEL`, `LOG_FORMAT` (json) |
| Almacenamiento S3 | `AWS_STORAGE_BUCKET_NAME`, `AWS_PRIVATE_STORAGE_BUCKET_NAME`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_S3_REGION_NAME`, `AWS_S3_ENDPOINT_URL`, `AWS_S3_CUSTOM_DOMAIN`, `AWS_DEFAULT_ACL`, `AWS_PUBLIC_MEDIA_LOCATION`, `AWS_PRIVATE_MEDIA_LOCATION` |
| Backups | `BACKUP_DIR`, `BACKUP_RETENTION_DAYS`, `BACKUP_S3_URI`, `BACKUP_AWS_*`, `BACKUP_S3_ENDPOINT_URL`, `BACKUP_DATABASE_URL` |
| Base de datos externa | `DATABASE_URL` (reemplaza a la del contenedor `db`), `DB_CONN_MAX_AGE` (60) |

---

## 5. Actualizar a una versión nueva

```bash
git pull
make backup            # siempre antes de migrar
make prod-build
make prod-up           # recrea los contenedores; el backend aplica las migraciones nuevas al arrancar
make prod-logs         # revisa que no haya errores
```

Para volver atrás: `git checkout <versión anterior> && make prod-build && make prod-up`; si la versión nueva migró
la base de datos de forma incompatible, restaura el backup previo (`make restore FILE=...`).

---

## 6. Backups y restauración

### Qué guarda `make backup`

`scripts/backup.sh` (lee `BACKUP_*` de `.env.prod`):

1. `pg_dump -Fc` de la base de datos, verificado con `pg_restore --list`.
2. Un `tar.gz` con la media pública (`/data/media`) y la privada (`/data/private`).
3. Un `.sha256` con las sumas de ambos archivos.
4. Borra las copias locales con más de `BACKUP_RETENTION_DAYS` días (14 por defecto).
5. Si hay `BACKUP_S3_URI` (`s3://bucket/prefijo`), sube los tres archivos (con el `aws` CLI del servidor o, si no
   está, con la imagen `amazon/aws-cli`). La retención en el bucket se define con una regla de ciclo de vida.

Los archivos quedan en `BACKUP_DIR` como `housetel-<fecha UTC>-db.dump`, `housetel-<fecha>-media.tar.gz` y
`housetel-<fecha>.sha256`, con permisos 600.

**La `FERNET_KEY` no va en el backup** (a propósito): guárdala en tu gestor de secretos. Una base restaurada con otra
llave pierde las credenciales guardadas de las integraciones (habría que volver a escribirlas).

Programa un backup diario con cron (hora del servidor):

```cron
15 3 * * * cd /srv/housetel && make backup >> /var/log/housetel-backup.log 2>&1
```

### Restaurar

```bash
make restore FILE=backups/housetel-20261001T031500Z-db.dump
```

`scripts/restore.sh` verifica las sumas, pide escribir `RESTORE`, detiene nginx/backend/worker/beat, recrea la base y
restaura el dump, repone la media del mismo backup (si existe) y vuelve a levantar todo. Prueba una restauración
**una vez al mes** en otro servidor o con otro proyecto (`PROD_PROJECT=housetel-restore-test`): un backup que nunca se
restauró no es un backup.

### Recomendación: PostgreSQL administrado con PITR

Para clientes que pagan, usa un PostgreSQL administrado con **recuperación a un punto en el tiempo (PITR)**: AWS RDS
o Aurora, Google Cloud SQL, Azure Database for PostgreSQL, DigitalOcean Managed Databases o Crunchy Bridge.

- PITR guarda el WAL continuamente: permite volver a cualquier segundo de los últimos 7–35 días (p. ej. justo antes
  de un borrado accidental), algo que un `pg_dump` diario no da (se pierde hasta un día de reservas).
- Activa backups automáticos con al menos 14 días de retención, cifrado en reposo, alta disponibilidad (standby en
  otra zona) si el presupuesto lo permite, y la extensión `btree_gist` (Housetel la necesita; los servicios
  administrados la permiten).
- Configura `DATABASE_URL=postgres://usuario:clave@host:5432/housetel?sslmode=require` en `.env.prod`. El servicio
  `db` del compose deja de usarse (puedes dejarlo apagado: `docker compose ... stop db`; `POSTGRES_PASSWORD` sigue
  siendo obligatoria en el archivo, aunque no se use).
- Mantén `make backup` como segunda línea: con `BACKUP_DATABASE_URL` igual a tu `DATABASE_URL`, el script hace el
  `pg_dump` con un contenedor `postgres:17` temporal; la media sigue saliendo del volumen (o, con S3, activa el
  versionado del bucket).

---

## 7. Almacenamiento de archivos

- **Por defecto**: volúmenes de Docker en el servidor. `media` (fotos de habitaciones, logos, imágenes del motor)
  la sirve nginx en `/media/photos/`, `/media/branding/` y `/media/booking-engine/`; cualquier otra ruta bajo
  `/media/` responde 404. `private_media` (documentos de identidad, firmas del check-in, facturas y XML de la DIAN,
  archivos SIRE, fotos de daños) solo la montan backend y worker: esos archivos salen únicamente por vistas de la API
  con sesión y permisos.
- **S3 compatible** (AWS S3, DigitalOcean Spaces, Cloudflare R2, MinIO): define `AWS_STORAGE_BUCKET_NAME` (fotos
  públicas) y, mejor, `AWS_PRIVATE_STORAGE_BUCKET_NAME` (privados; si falta, van al mismo bucket bajo `private/` con
  ACL privada). El bucket público necesita lectura pública (política o CDN) y su dominio en `NGINX_CSP_IMG_SRC`
  (p. ej. `https://housetel-media.s3.amazonaws.com` o tu `AWS_S3_CUSTOM_DOMAIN`). El bucket privado **nunca** debe
  ser público: Housetel lo lee con credenciales y lo entrega por la API.
- Con S3 configurado, las fotos públicas **y** los archivos privados siguen esa configuración: los storages de
  documentos de huéspedes, firmas, fotos de daños, facturas y SIRE heredan del storage privado común de
  `apps.core.storage` (P-INT). Sin S3, los privados van al volumen `private_media`.

---

## 8. Monitoreo

- **Sentry** (opcional): `SENTRY_DSN` captura los errores del API, del worker y de beat (integraciones de Django,
  Celery y Redis). No envía datos personales (`send_default_pii=False`). `SENTRY_TRACES_SAMPLE_RATE` (0 por defecto)
  activa trazas de rendimiento.
- **Salud** para monitores externos (UptimeRobot, Better Stack, el balanceador):
  - `GET /healthz` (nginx vivo);
  - `GET /api/v1/public/core/health/` (Django vivo, sin tocar la base);
  - `GET /api/v1/public/core/health/ready/` (PostgreSQL y Redis responden; **503** si alguno falla). No revela el
    motivo; el detalle queda en el log.
- **Logs**: `make prod-logs` (JSON por línea). Cada petición tiene un `request_id` en el log de nginx, en el de
  Django y en la cabecera `X-Request-ID` de la respuesta: con él se sigue un error de punta a punta.
- **Alertas de negocio**: la campana de la app y `/app/alerts` (automatizaciones fallidas, integraciones caídas).

---

## 9. Probar el stack de producción en tu máquina

Sin dominio ni TLS, con un archivo de entorno desechable fuera del repositorio (claves generadas al azar,
`FRONTEND_URL=http://localhost:<puerto>`, redirección a https apagada):

```bash
scripts/prod-local-env.sh /tmp/housetel-prod.env 8080          # puerto opcional (8080 por defecto)
make prod-build prod-up PROD_ENV_FILE=/tmp/housetel-prod.env
# http://localhost:8080 — regístrate en /signup o crea el super-admin:
make prod-createsuperuser PROD_ENV_FILE=/tmp/housetel-prod.env
make prod-down PROD_ENV_FILE=/tmp/housetel-prod.env
docker compose -p housetel-prod -f docker-compose.prod.yml --env-file /tmp/housetel-prod.env down -v   # borra sus datos
```

`DJANGO_SECURE_SSL_REDIRECT=0` solo para esta prueba (sin él, Django redirige todo a https). Las cookies `Secure`
funcionan en `http://localhost` en Chrome, Firefox y curl.

---

## 10. Checklist de seguridad

- [ ] `.env.prod` con permisos 600, fuera de git; `FERNET_KEY` y `DJANGO_SECRET_KEY` también en el gestor de secretos.
- [ ] TLS válido y `NUM_PROXIES` correcto (prueba: 11 logins fallidos seguidos desde tu IP → el 11.º responde 429).
- [ ] HSTS: se envía por un año, con subdominios y `preload` (Django y nginx). Antes de activarlo en un dominio con
      otros subdominios, confirma que **todos** sirven HTTPS; para empezar con prudencia usa
      `DJANGO_HSTS_SECONDS=3600` y `NGINX_HSTS="max-age=3600"` y súbelos después.
- [ ] `ADMIN_ENABLED=0` salvo mantenimiento puntual; `API_DOCS_PUBLIC=0`.
- [ ] `HOUSETEL_ALLOW_SIMULATIONS=0` (el menú no muestra simuladores; `/api/v1/public/finance/sim/...` da 404).
- [ ] Backups diarios programados, copia fuera del servidor y una restauración de prueba al mes.
- [ ] Sentry y un monitor de `/api/v1/public/core/health/ready/`.
- [ ] Firewall: solo 22 (SSH con llave) y 80/443 abiertos; PostgreSQL y Redis nunca expuestos (el compose no los publica).
- [ ] Actualizaciones de seguridad del sistema operativo y reconstrucción periódica de las imágenes (`make prod-build`).

---

## 11. Problemas frecuentes

| Síntoma | Causa y solución |
|---|---|
| El backend no arranca: `Production settings are incomplete: …` | Falta la variable que dice el mensaje (o `DJANGO_DEBUG=1`). |
| `400 Bad Request` en todas las páginas de la API | El host no está en `DJANGO_ALLOWED_HOSTS` (por defecto solo el de `FRONTEND_URL`). |
| `403 csrf_failed` al iniciar sesión | El origen del navegador no coincide con `FRONTEND_URL` ni con `CSRF_TRUSTED_ORIGINS`. |
| Bucle de redirecciones | El proxy TLS no envía `X-Forwarded-Proto: https` (o termina TLS y habla http a nginx sin esa cabecera). |
| Todos quedan bloqueados por "demasiados intentos" a la vez | `NUM_PROXIES` bajo: DRF ve la IP del proxy como si fuera de todos. Súmale 1 por proxy delante de nginx. |
| Fotos rotas con S3 | Falta el dominio del bucket/CDN en `NGINX_CSP_IMG_SRC`, o el bucket público no es legible. |
| Una integración queda "desactivada" tras configurarla | Se activa sola al completar sus credenciales; si la desactivaste a mano, vuelve a activarla en su hoja de configuración. |
| Pagos: "las simulaciones están desactivadas en este entorno" | Ese hotel tiene la integración en modo simulado: pásala a real con sus llaves de Wompi. |
