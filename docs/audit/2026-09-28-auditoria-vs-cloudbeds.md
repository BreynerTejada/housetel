# Auditoría Housetel vs Cloudbeds (28-sep-2026)

Informe de un agente auditor de producto y UX, más los hallazgos de la validación E2E en Chrome (Fase E) del orquestador. Es la base de la Fase P (piloto): `docs/superpowers/plans/2026-09-28-housetel-pilot.md`.

## Veredicto

- El producto está mucho más completo y pulido de lo esperable en un MVP:
  - UI en español con el inglés al 100 %.
  - Adaptable al celular y rápida.
  - Cubre el día a día de recepción, limpieza, tarifas, portal del huésped y lo legal colombiano.
- Paridad estimada con lo que un hotel pequeño o un hostal colombiano usa de Cloudbeds: ~80 %. Para hoteles medianos y cadenas (mucho OTA, clientes corporativos): ~50–60 %.
- **No es operable en producción hoy**:
  - Pagos, DIAN, TRA, WhatsApp y OTAs están simulados o sin probar en vivo.
  - No hay despliegue de producción, backups ni monitoreo.
  - No hay recuperación ni cambio de contraseña.
  - La fase C no tiene tests corridos.
- **Piloto controlado con 1–3 hoteles:** viable tras ~3–4 semanas de endurecimiento. **Vender a clientes que pagan:** faltan ~2–3 meses.

## Matriz de paridad

| Capacidad | Estado | Evidencia |
|---|---|---|
| PMS núcleo (Hoy, reservas, check-in/out, folio, caja, auditoría nocturna) | Tiene; auditoría automática **Mejor** | `/app`, `/app/reservations/:id`, `/app/cashier`, `/app/night-audit` |
| Calendario con DnD (incluye camas de hostal) | Tiene | `ExclusionConstraint` en `bookings/models.py` hace imposible la doble asignación |
| Reservas multi-habitación, grupos, cupos | **Falta en UI** | El asistente hace una sola estadía; no hay UI para `bookings/groups/` |
| Folios divididos, cuentas casa/empresa, facturar a un NIT | Parcial | La factura siempre sale al titular (`compliance/services/builder.py::invoice_customer`) |
| Housekeeping y mantenimiento en celular | **Mejor** | `/app/housekeeping/mine`, auto-asignación, tickets con foto que bloquean la habitación |
| Tarifas (grilla, derivados, restricciones, promos) | Tiene | `/app/rates*` |
| Revenue | Parcial | Reglas + IA; no usa datos de competencia o mercado (como PIE/Signals de Cloudbeds) |
| Channel manager | **Falta en real** | Solo iCal real y simuladores; Channex sin probar y no pasaría certificación (rangos, 500 días en ≤2 llamadas, webhooks) |
| Booking engine y widget | Tiene | `/h/:slug`, `/embed/:slug`; sin constructor de sitio web ni metabuscadores |
| Marketplace B2C propio | **Mejor** | Cloudbeds no lo tiene; sin reseñas ni mapa |
| Pagos | Parcial | Wompi programado pero sin probar; no guarda tarjetas, no cobra no-shows, no maneja tarjetas virtuales de OTA ni datáfono |
| Mensajería | Parcial | Email y WhatsApp Cloud (sin probar); no ingiere mensajes de OTAs ni correo entrante |
| Check-in online y portal del huésped | **Mejor** | Datos TRA, documento, firma, pago y extras, incluido en todos los planes |
| Legal Colombia | **Mejor en diseño**, simulado | Nativo; Factus y TRA sin probar; formato SIRE inferido |
| Reportes | Parcial | 18 reportes exportables sobre fecha de negocio; sin constructor ni consolidado |
| IA | **Mejor** | Copiloto con confirmación, chatbot público, onboarding, anomalías; la cuota gratuita de Gemini (20/día) es compartida |
| Multi-propiedad | Parcial | Hay selector de propiedad; no hay tableros ni reportes consolidados |
| App móvil | Parcial | Web adaptable; sin PWA, modo offline ni push |
| Integraciones y API | **Falta** | Sin API keys ni webhooks salientes |
| Onboarding | **Mejor**, sin importación | Signup + prueba + IA + checklist; no importa datos de otro PMS |
| Soporte y documentación | **Falta** | Sin centro de ayuda ni canal de soporte |
| Precio | **Mejor** | Público y todo incluido: $149.000 / $349.000 / $899.000 COP al mes |

## Bloqueantes para clientes reales

**Crítico**
1. La simulación viene por defecto y queda expuesta: el endpoint público `POST /api/v1/public/finance/sim/intents/<ref>/decide/` aprueba pagos, y los simuladores aparecen en el menú.
2. No hay entorno de producción:
   - `DEBUG` y `ALLOWED_HOSTS=["*"]` por defecto.
   - Sin HSTS, cookies `Secure` ni CSP.
   - Sin CI, backups ni Sentry.
   - Documentos privados en disco local.
3. Ningún proveedor real está validado (Wompi, Factus, TRA, WhatsApp, Channex).
4. Cuentas incompletas: sin recuperar o cambiar contraseña, sin verificación de email, sin 2FA.
5. No hay red de seguridad: la fase C no tiene tests corridos y `reports`, `saas` y `control` tienen 0 tests.

**Alto**
6. No se pueden hacer reservas multi-habitación ni grupos desde el PMS.
7. Facturación corporativa: no se factura a empresa, no se divide el folio y no hay cartera.
8. No hay migración: no se importan reservas, huéspedes ni tarifas.
9. Legal del SaaS y Habeas Data:
   - La casilla de términos no enlaza a ningún documento.
   - No hay política de datos ni DPA.
   - Documentos y firmas se guardan para siempre.
   - Los links del portal no vencen.
   - Housetel no emite su propia factura electrónica.
10. No se guardan tarjetas ni se cobran no-shows; no se manejan tarjetas virtuales de OTA.
11. No existe canal de soporte.

**Medio**
12. La cuota de IA es compartida: el copiloto gasta ≥2 llamadas por pregunta.
13. Seguridad:
    - La protección SSRF de iCal no resuelve DNS.
    - `/api/schema/` y `/django-admin/` son públicos.
    - `NUM_PROXIES` no está configurado.
    - El check-in no devuelve 409 si la habitación sigue ocupada.
14. Falta correo transaccional con SPF/DKIM y verificación de WhatsApp por hotel.
15. Las traducciones pesan 540 KB y se cargan en todas las páginas públicas.
16. No hay vista consolidada para cadenas.

## Usabilidad

**Bien resuelto**
- Estable y pulido: sin desbordes ni errores de consola a 1440 y 375 px; APIs de 45–160 ms.
- Panel Hoy de primer nivel; limpieza en celular con botones grandes.
- Permisos y errores bien resueltos; 6.707 claves de traducción, iguales en español e inglés.

**A corregir**
- Los simuladores y el aviso "7 de 9 en simulado" son visibles para el hotel.
- El asistente de reserva solo maneja una habitación.
- Checkout móvil (`/book/:slug`, 375 px): el total queda debajo del botón "Confirmar".
- La burbuja del chatbot tapa botones a 375 px (el "Pagar" del portal y el país de residencia del checkout).
- Textos:
  - "1 movimientos", "1 archivo(s)" (`compliance/services/sire.py`).
  - Las alertas no se traducen.
  - El 404 de la API sale en inglés.
  - El título de `/search` sale en minúscula.
- El token `text-subtle` tiene contraste 3,1:1 en claro y 3,6–4,0:1 en oscuro, por debajo del 4,5:1 de AA.
- 240–426 recomendaciones de precio pendientes.
- Contabilidad aterriza en Calendario.

## Hallazgos de la validación en Chrome (orquestador)

Resultado: los 15 flujos del spec §10.1 funcionan. Capturas en `docs/e2e-screenshots/`.

1. **(Corregido)** El asistente de reserva mostraba el total con IVA aunque el titular fuera extranjero no residente; ahora recotiza al elegir el titular.
2. Calendario: la etiqueta del mes ("SEP"/"OCT") se monta sobre el día de la semana en los cambios de mes.
3. Revenue: la explicación dice "el precio se queda en $441.600" y el recomendado es $441.000 (el redondeo no se explica).
4. Onboarding IA: el desayuno aparece duplicado en los extras propuestos.
5. Hoy en móvil: los nombres de huéspedes se cortan demasiado.
6. Automatizaciones: con "Ejecutar ahora" la corrida funciona, pero el aviso puede no verse si termina muy rápido.
7. Gemini free tier: la cuota se agota rápido; el fallback simulado funciona y lo avisa.

## Dónde ya supera a Cloudbeds

- Cumplimiento colombiano nativo: DIAN, SIRE y TRA alimentados por el check-in online.
- 20 automatizaciones visibles, auditoría con deshacer, detección de anomalías y auditoría nocturna automática.
- IA que propone y pide confirmación, chatbot que cotiza y onboarding asistido.
- Precio público todo incluido en COP; check-in online incluido; PSE y Nequi.
- Inventario protegido en la base de datos y reportes sobre fecha de negocio.
- Marketplace propio, hostal por camas e interfaz moderna, bilingüe y adaptable al celular.

## Hoja de ruta

**Imprescindible antes del primer cliente real**
- Producción segura.
- Apagar simulaciones en producción.
- Recuperar y cambiar contraseña; verificar email.
- Validar en vivo Wompi, Factus, TRA y SIRE con el hotel piloto.
- Pilotos con iCal o con su channel manager actual.
- Tests de dinero, inventario y facturación; suites en verde.
- Términos, política de datos, DPA y factura propia de Housetel.
- Importación asistida.
- Soporte por WhatsApp.
- Reservas multi-habitación y facturar a empresa.

**Después**
- Channex certificado.
- Tokenización de tarjetas, cobro de no-shows y tarjetas virtuales de OTA.
- Folios divididos avanzados, cartera y grupos con cupos.
- Centro de ayuda.
- Vista consolidada para cadenas.
- PWA con notificaciones push.
- Metabuscadores y reseñas.
- API pública e integraciones (Siigo/Alegra, POS, cerraduras).
- IA con plan pago.
- Traducciones divididas y accesibilidad AA.
