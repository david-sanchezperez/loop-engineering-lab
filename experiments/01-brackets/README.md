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
El backend Muse requiere el servidor llama.cpp corriendo en `http://localhost:8080`
con el modelo `muse-glimmer-30b` cargado.

### Ejecución completa (los tres backends)

```bash
export ANTHROPIC_API_KEY=sk-...
bash run_comparison.sh 5        # 5 ejecuciones por backend (default)
bash run_comparison.sh 10 15    # 10 ejecuciones, máx 15 iteraciones c/u
```

### Solo un backend

```bash
python loop.py --backend local --runs 5 --max-iters 10
python loop.py --backend claude --runs 5 --max-iters 10 --budget-usd 0.05
python loop.py --backend muse --runs 5 --max-iters 10
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

## Configuración de los modelos

| Modelo | Backend | Servidor | Parámetros |
|--------|---------|----------|------------|
| Qwen3-35B | `local` (llama-cpp-python / LiteLLM) | `localhost:4000` | `max_tokens=3000`, `temperature=0.7` |
| Claude Haiku 4.5 | `claude` (Anthropic API) | API externa | `max_tokens=3000`, `temperature=0.7` |
| Muse-Glimmer-30B-GGUF | `muse` (llama-cpp-python / llama.cpp) | `localhost:8080` | `max_tokens=3000`, `temperature=0.7` |

### Muse-Glimmer-30B-GGUF (backend `muse`)

El backend Muse usa el modelo [Muse-Glimmer-30B-GGUF](https://huggingface.co) cargado con
llama-cpp-python, que se conecta a un servidor llama.cpp expuesto vía API compatible con OpenAI.

**Requisitos:**

```bash
# Iniciar el servidor llama.cpp (ejemplo con modelo GGUF)
# El modelo debe estar disponible en el path indicado
llama-server \
    -m /path/to/muse-glimmer-30b.Q4_K_M.gguf \
    --port 8080 \
    --host 127.0.0.1
```

**Variables de entorno:**

| Variable | Valor por defecto | Descripción |
|----------|-------------------|-------------|
| `MUSE_BASE_URL` | `http://localhost:8080/v1` | Endpoint del servidor llama.cpp |
| `MUSE_API_KEY` | `sk-not-required` | API key (llama.cpp no la requiere realmente) |
| `MUSE_MODEL` | `muse-glimmer-30b` | Identificador del modelo en el servidor |

**Consideraciones:**

- La inferencia es 100% local, sin coste monetario.
- La latencia depende del hardware local (GPU recomendada).
- El modelo no tiene limitación de presupuesto en el código — el freno de presupuesto
  solo aplica al backend Claude.

---

## Resultados comparativos de 3 modelos (n=5 ejecuciones)

| Métrica | Claude Haiku 4.5 | Qwen3-35B (local) | Muse-Glimmer-30B (local) |
|---------|-----------------|-------------------|--------------------------|
| Tasa de éxito | 100% (5/5) | 100% (5/5) | — (pending) |
| Iteraciones promedio | 1.0 | 1.8 | — (pending) |
| Rango de iteraciones | 1–1 | 1–3 | — (pending) |
| Tiempo promedio | 1.3 s | 72.5 s | — (pending) |
| Costo promedio | $0.00078 | $0 (local) | $0 (local) |

Claude Haiku resuelve la tarea correctamente en la primera iteración siempre.
Qwen3-35B local necesita 1–3 intentos (media 1.8) porque su modo de reasoning a veces
llega a una solución por conteo antes de corregirse con un stack. Ambos modelos
alcanzan el 100% de éxito.

La diferencia de tiempo (1.3s vs 72.5s) refleja el thinking overhead de Qwen3 más la
latencia de red a Anthropic frente a inferencia local.

Muse-Glimmer-30B-GGUF se ejecuta completamente en local vía llama.cpp.
Los resultados pending se llenarán al ejecutar el servidor y lanzar el experimento.

---

## Frenos activos en este experimento

| Freno | Valor por defecto | Aplica a |
|-------|------------------|----------|
| Step cap | 10 iteraciones | Todos los backends |
| Circuit breaker | 3 errores iguales seguidos | Todos los backends |
| Heartbeat | Cada iteración | Todos los backends |
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

- **Muse-Glimmer-30B es un modelo eficiente:** corre completamente local con llama.cpp.
  Su arquitectura optimizada lo hace competitivo en latencia con modelos más pequeños,
  aunque con capacidades de reasoning menores que Qwen3. Los resultados pending
  se llenarán al ejecutar el servidor.

- **Claude Haiku 4.5:** se eligió el modelo más económico de Claude para
  mantener el costo del experimento bajo. Un experimento con Sonnet o Opus
  mostraría resultados diferentes.
