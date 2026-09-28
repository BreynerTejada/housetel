# Reanudar la Fase C (modo MVP)

Pausada a pedido del usuario (2026-09-27). Todo el trabajo está commiteado en la rama `wip/phase-c`, sobre `main` = Fase B `12ed93d`. Es **modo MVP**: los agentes no escriben ni corren tests (decisión del usuario). Los tests se escriben después de validar todo en Chrome. `manage.py check` estaba limpio al pausar.

## Estado (workflow `housetel-phase-c-mvp`, run `wf_e36b971c-907`)

| Tarea | Estado |
|---|---|
| C1 … C13 | **terminadas** (notas `C<n>-*.md` con "Cómo probarlo en la UI") |
| C-INT integración | **terminada** (2026-09-28): ver `C-INT.md` (verificado, corregido, pendientes y checklist consolidado para Chrome) |
| Commit de la fase, Fase E (validación en Chrome), luego fase de tests | pendientes |

## Cómo reanudar

1. `git switch wip/phase-c && git reset main && git switch main`. El WIP vuelve como cambios sin commitear sobre `main`, para que los agentes lo encuentren con `git status` / `git diff`.
2. `docker compose up -d` si está detenido; luego `docker compose exec -T backend python manage.py check`.
3. `systemd-inhibit --what=sleep:idle --mode=block --who="Housetel build (Claude Code)" --why="agentes" sleep infinity` en segundo plano, para que la laptop no se suspenda.
4. Relanzar **sin editar el script**, para conservar la caché de las 9 tareas terminadas: `Workflow({scriptPath: "<carpeta de workflows>/housetel-phase-c-mvp-wf_e36b971c-907.js", resumeFromRunId: "wf_e36b971c-907"})`. Solo se re-ejecutan C13, C10, C11 y C12 (su prompt ya trae la nota de REANUDACIÓN) y luego C-INT.
5. Al terminar: commit, Fase E (validación en Chrome con el checklist de `C-INT.md`), correcciones y, al final, la fase de tests.

> Tras C-INT ya no hace falta reanudar el workflow: el siguiente paso es el commit y la Fase E.
