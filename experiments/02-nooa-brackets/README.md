# Experimento 02 — NOOA vs. Tool-Calling Clásico

**Tarea (compartida con el experimento 01):** implementar `is_balanced(s)` que
detecta si los brackets `()`, `[]`, `{}` están correctamente anidados. El edge
case `"([)]"` fuerza iteraciones reales cuando el modelo no usa un stack.

**Pregunta del experimento:** ¿cambia la efectividad del agente según la
*arquitectura* del loop, con tarea / checker / frenos idénticos?

- **NOOA (`nooa_agent.py`):** el agente ES un objeto Python. Sus métodos
  públicos son las acciones (`submit_solution(code)`, `view_test_cases()`,
  `finish()`); el docstring de cada método ES el prompt de esa acción. El
  harness introspecciona la clase con `inspect` y arma una descripción textual
  de la interfaz (NO un schema JSON). Backend-agnostic: funciona con
  completions planos, sin depender del tool-use nativo del modelo.
- **Clásico (`classic_tools.py`):** las mismas acciones se definen como
  herramientas con schema JSON y se invocan mediante el tool-calling *nativo*
  del backend. Ambos despachan a las mismas acciones subyacentes.

Ambos reusan el mismo checker (`checker.py`) y los mismos frenos (`brakes.py`),
implementados una sola vez.

> **Estado del scaffold:** este README es un esqueleto. La documentación
> completa — setup del entorno, cómo ejecutar (ambos enfoques, todos los
> backends incluido el mock), tabla de métricas, tabla de frenos, explicación
> detallada de NOOA vs. clásico, tabla + gráfico de resultados comparativos y
> limitaciones — se completa una vez listo el harness y recolectados los
> resultados (ver `docs/bitacora.md`, entrada 02).

---

## Estructura

| Archivo | Rol | Estado |
|---------|-----|--------|
| `checker.py` | Juez determinista (tests de brackets en subproceso aislado), compartido | ✅ |
| `brakes.py` | Frenos compartidos (step cap, circuit breaker, heartbeat, budget Claude-only) | ✅ |
| `skills/balanced_brackets/SKILL.md` | Prompt/tarea (reusado del experimento 01) | ✅ |
| `nooa_agent.py` | Agente-objeto + introspección + parseo/despacho | ⏳ |
| `classic_tools.py` | Tools (JSON schema) + despacho nativo | ⏳ |
| `loop.py` | Harness CLI (`--approach`, `--backend`, `--runs`, `--max-iters`, `--budget-usd`) | ⏳ |
| `plot.py` | Gráfico NOOA vs. clásico → `results/comparacion.png` | ⏳ |
| `run_comparison.sh` | Lanza N ejecuciones de cada enfoque y regenera el gráfico | ⏳ |
| `tests/` | Unit tests pytest de las piezas offline | ⏳ |
| `results/` | `{approach}_runs.json`, `loop_state.json`, `comparacion.png` | ⏳ |

---

## Qué medirá este experimento

| Métrica | Descripción |
|---------|-------------|
| `iterations` | Pasos que necesitó el agente para pasar todos los tests |
| `success` | Si la ejecución terminó con código correcto |
| `stop_reason` | `success`, `step_cap`, `circuit_breaker`, o `budget` (solo Claude) |
| `wall_time_s` | Tiempo total de la ejecución en segundos |
| `input_tokens` | Tokens de entrada acumulados (no aplica a backend local) |
| `output_tokens` | Tokens de salida acumulados (no aplica a backend local) |
| `cost_usd` | Costo en USD (solo backend Claude) |

## Frenos activos (compartidos, `brakes.py`)

| Freno | Valor por defecto | Aplica a |
|-------|------------------|----------|
| Step cap | 10 iteraciones | Todos los backends |
| Circuit breaker | 3 errores iguales seguidos | Todos los backends |
| Heartbeat | Cada iteración → `loop_state.json` | Todos los backends |
| Budget ceiling | $0.10 USD | Solo Claude |
