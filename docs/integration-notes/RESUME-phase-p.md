# Reanudar la Fase P (piloto real, modo MVP)

Detenida a pedido del usuario (2026-09-28, 06:4x). El progreso está commiteado en la rama **`wip/phase-p`**, sobre `main` (`35e1db6`). Al detenerla, `manage.py check` estaba limpio, había 0 migraciones pendientes y el stack de desarrollo quedó arriba con el seed (4 propiedades, 3.377 reservas).

## Estado (workflow `housetel-phase-p`, run `wf_e1a00a60-f3f`)

| Tarea | Estado |
|---|---|
| P1 producción/seguridad/modo real | **terminada** (resultado en caché; notas `P1-production.md`) |
| P2 cuentas | **terminada** (`P2-accounts.md`) |
| P3 multi-habitación/grupos/cupos | **terminada** (`P3-groups-multiroom.md`) |
| P4 facturación corporativa/cartera | **terminada** (`P4-corporate-billing.md`) |
| P5 importador | **terminada** (`P5-imports.md`) |
| P6 pulido/legal/integraciones guiadas | **terminada** (`P6-polish.md`) |
| **P-INT integración** | **interrumpida**: había empezado (reinició el stack, cargó los datos) pero no escribió `P-INT.md` |

## Cómo reanudar

1. `git switch wip/phase-p` (seguir trabajando en esta rama; al terminar se integra a `main`).
2. `docker compose up -d` si está detenido; luego `docker compose exec -T backend python manage.py check`.
3. `systemd-inhibit --what=sleep:idle --mode=block --who="Housetel build (Claude Code)" --why="agentes" sleep infinity` en segundo plano. Mantener la tapa abierta: cerrarla suspende de todos modos.
4. Relanzar el workflow con su `scriptPath` (`housetel-phase-p-wf_e1a00a60-f3f.js` en la carpeta de workflows de la sesión) y `resumeFromRunId: "wf_e1a00a60-f3f"`:
   - las 6 tareas terminadas salen de caché;
   - solo corre **P-INT**;
   - opcional: agregar al prompt de P-INT la nota "retoma: ya había empezado; revisa el estado actual antes de rehacer pasos". Editar solo ese prompt no invalida la caché de P1–P6.
5. Después: commit, validación en Chrome de las funciones nuevas (checklist de `P-INT.md`) y fase de tests.
