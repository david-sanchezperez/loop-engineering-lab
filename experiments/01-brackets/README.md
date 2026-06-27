# Experimento 01 — Brackets Balanceados

**Tarea:** implementar `is_balanced(s)` que detecta si los brackets `()`, `[]`,
`{}` en una cadena están correctamente anidados.

**Por qué no el palíndromo:** cualquier modelo competente resuelve
`s == s[::-1]` en la primera iteración. El loop nunca corre, no hay nada que
demostrar. `is_balanced` tiene el edge case `"([)]"` — cadena con conteos
iguales de brackets pero orden incorrecto — que rompe soluciones naive y fuerza
iteraciones reales cuando el modelo no usa un stack.

---

## Cómo ejecutarlo

### Prerequisitos

```bash
pip install -r ../../requirements.txt
```

El backend local requiere LiteLLM corriendo en `http://localhost:4000` con
el modelo `qwen3`. El backend Claude requiere `ANTHROPIC_API_KEY` en el entorno.

### Ejecución completa (ambos backends)

```bash
export ANTHROPIC_API_KEY=sk-...
bash run_comparison.sh 5        # 5 ejecuciones por backend (default)
bash run_comparison.sh 10 15    # 10 ejecuciones, máx 15 iteraciones c/u
```

### Solo un backend

```bash
python loop.py --backend local --runs 5 --max-iters 10
python loop.py --backend claude --runs 5 --max-iters 10 --budget-usd 0.05
```

### Regenerar gráfico sin lanzar experimentos

```bash
python plot.py
```

---

## Qué mide este experimento

| Métrica | Descripción |
|---------|-------------|
| `iterations` | Cuántos intentos necesitó el modelo para pasar todos los tests |
| `success` | Si la ejecución terminó con código correcto |
| `stop_reason` | `success`, `step_cap`, `circuit_breaker`, o `budget` (solo Claude) |
| `wall_time_s` | Tiempo total de la ejecución en segundos |
| `cost_usd` | Costo en USD (solo backend Claude) |

---

## Frenos activos en este experimento

| Freno | Valor por defecto | Aplica a |
|-------|------------------|----------|
| Step cap | 10 iteraciones | Ambos backends |
| Circuit breaker | 3 errores iguales seguidos | Ambos backends |
| Heartbeat | Cada iteración | Ambos backends |
| Budget ceiling | $0.10 USD | Solo Claude |

---

## Limitaciones

- **Tarea trivial a propósito:** `is_balanced` es un problema clásico que
  modelos grandes conocen bien. El objetivo es validar el harness, no probar
  los límites del modelo. Los experimentos siguientes usarán tareas más complejas.

- **Una sola tarea por ejecución:** cada ejecución parte de cero (prompt inicial
  fresco). No hay memoria entre ejecuciones — esto es intencional para que cada
  ejecución sea independiente y los resultados sean comparables.

- **Sin paralelismo:** las ejecuciones son secuenciales. En un sistema real se
  podrían ejecutarse en paralelo, pero eso complicaría la comparación de tiempos.

- **Qwen3 es un modelo de reasoning:** el modelo local usa thinking antes de
  responder (`reasoning_content` separado del `content`). Esto lo hace más
  lento pero potencialmente más preciso. Los tiempos de Qwen3 reflejan esto.

- **Claude Haiku 4.5:** se eligió el modelo más económico de Claude para
  mantener el costo del experimento bajo. Un experimento con Sonnet o Opus
  mostraría resultados diferentes.
