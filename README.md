# loop-engineering-lab

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)

> **TL;DR** — Loop engineering means designing the *system around the agent*, not just the prompt.
> This repo is a growing lab of experiments: each one runs a real agent loop, measures it with
> deterministic tests, and shows what happens when you add proper brakes (step cap, circuit breaker,
> heartbeat, budget ceiling). Experiment 01 compares Claude Haiku vs. Qwen3-35B local on a
> bracket-balancing task where naive solutions reliably fail.

---

## Qué es loop engineering

Loop engineering es diseñar el sistema que rodea a un agente, no solo el prompt que se le da.
Tiene dos mitades inseparables: el **motor** (hacer que el agente actúe sobre algo real, observe
el resultado real, y decida solo cuándo parar) y los **frenos** (limitar explícitamente cuánto
daño puede hacer mientras nadie lo está mirando).

Un agente sin motor es un chatbot. Un agente sin frenos es un sistema que puede iterar hasta el
infinito, gastar dinero ilimitado, o romper cosas en silencio. Loop engineering es tener ambas
mitades a la vez, con las 6 piezas necesarias: estado persistente, automatización, aislamiento
(blast radius), skills, conectores, y sub-agentes maker/checker.

→ Explicación completa en [`docs/loop-engineering-explicado.md`](docs/loop-engineering-explicado.md)

---

## Experimentos

| # | Tarea | Modelos | Estado |
|---|-------|---------|--------|
| [01 — Brackets](experiments/01-brackets/) | `is_balanced(s)`: detectar brackets balanceados | Qwen3-35B local vs. Claude Haiku 4.5 | ✓ Completo |

*Más experimentos próximamente: tareas más complejas, herramientas externas via MCP, loops multi-agente.*

---

## Resultados: Qwen3-35B local (n=5)

> Claude Haiku pendiente de créditos API — se actualizará con resultados reales.

| Métrica | Qwen3-35B (local) |
|---------|-------------------|
| Tasa de éxito | 100% (5/5) |
| Iteraciones promedio | 1.8 |
| Rango de iteraciones | 1–3 |
| Tiempo promedio | 72.5 s |

El modelo local resuelve la tarea correctamente en todas las corridas, pero no siempre en el
primer intento — el edge case `"([)]"` (brackets con conteos iguales pero orden incorrecto) rompe
las soluciones naive que no usan un stack.

![Comparación](experiments/01-brackets/results/comparacion.png)

---

## Estructura

```
loop-engineering-lab/
├── docs/
│   └── loop-engineering-explicado.md   # teoría completa con ejemplos del código
└── experiments/
    └── 01-brackets/
        ├── loop.py                     # harness con los dos backends y los 4 frenos
        ├── plot.py                     # genera comparacion.png
        ├── run_comparison.sh           # corre N corridas y genera el gráfico
        ├── skills/balanced_brackets/
        │   └── SKILL.md               # especificación de la tarea (fuera del código)
        └── results/
            ├── local_runs.json
            ├── claude_runs.json        # se genera al correr con ANTHROPIC_API_KEY
            └── comparacion.png
```

---

## Cómo correrlo

```bash
pip install -r requirements.txt

# Solo backend local (Qwen3 via LiteLLM en localhost:4000)
cd experiments/01-brackets
python3 loop.py --backend local --runs 5

# Ambos backends
export ANTHROPIC_API_KEY=sk-...
bash run_comparison.sh 5
```

---

## Diseño del harness

El freno de presupuesto existe **literalmente solo** en el backend Claude — no hay una variable
`budget` en el código del backend local, porque allí no hay costo real. Esta separación es
intencional: un freno que no aplica no debe existir en el código path donde no aplica.

El "checker" es el intérprete de Python corriendo tests deterministas, no el modelo
evaluándose a sí mismo. La separación maker/checker es lo que hace que el loop converja
en vez de que el modelo siempre diga que sí.
