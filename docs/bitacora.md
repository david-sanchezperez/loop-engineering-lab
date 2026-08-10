# Bitácora del laboratorio — loop-engineering-lab

Este archivo es la memoria persistente del repo: qué se hizo, qué está en
curso, y qué sigue. Vive en `docs/bitacora.md`.

**Instrucción para Claude Code: lee este archivo completo antes de empezar
cualquier experimento nuevo. Al cerrar uno, actualiza su estado aquí mismo
(no lo dejes solo en el README del experimento) y haz commit de ese cambio
por separado, con mensaje tipo `docs: actualizar bitácora tras cerrar 0X`.**

Leyenda de estado: `🔲 pendiente` · `🔄 en curso` · `✅ hecho`

---

## Hechos

### 01 — Brackets balanceados
**Estado:** ✅ hecho — ver `experiments/01-brackets/`

Harness con 4 frenos (step cap, circuit breaker, heartbeat, techo de
presupuesto solo en backend Claude), comparando Claude Haiku 4.5 vs. Qwen3-35B
local cuantizado en la tarea `is_balanced(s)`. Se eligió esta tarea sobre
el palíndromo porque el edge case `"([)]"` rompe soluciones naive por conteo,
forzando iteraciones reales de corrección. Verificación objetiva mediante
tests deterministas en subproceso aislado (no auto-evaluación del modelo).

Resultados reales (5 ejecuciones por backend):
- Claude Haiku 4.5: 100% éxito, 1 iteración siempre, 1.3s avg, $0.00078/ejecución
- Qwen3-35B local: 100% éxito, 1.8 iteraciones avg (rango 1–3), 72.5s avg

Resultados en `experiments/01-brackets/results/`.

---

## Backlog (orden sugerido, no obligatorio)

### 02 — NOOA vs. tool-calling clásico (arquitectura del loop)
**Estado:** 🔄 en curso
**Carpeta destino:** `experiments/02-nooa-brackets/`

**Por qué ahora:** el experimento 01 dejó un harness funcional con un único
patrón de loop (el modelo devuelve código en un bloque de código python, el
harness lo extrae y lo prueba). La pregunta natural es si la *forma* en que
el agente invoca sus acciones cambia su efectividad: ¿un agente que ES un
objeto Python (NOOA — Natural Object-Oriented Agents) se comporta distinto
a uno que usa el tool-calling nativo del backend? Este experimento aísla esa
variable manteniendo constantes la tarea, el checker y los frenos, para que
la diferencia observada se atribuya a la arquitectura del agente y no a la
tarea ni al juez.

**Objetivo didáctico:** mostrar dos arquitecturas de loop resolviendo la
misma tarea y medirlas con la misma vara (tasa de éxito, pasos, costo de
tokens), evidenciando el trade-off portabilidad-vs-robustez entre un agente
orientado a objetos (backend-agnostic, sin dependencia de tool-use nativo) y
uno que explota el tool-calling nativo del modelo.

**Diseño concreto — dos enfoques sobre la misma tarea (`is_balanced`):**

- **NOOA (`nooa_agent.py`):** el agente ES un objeto Python. Sus métodos
  públicos son las acciones disponibles (`submit_solution(code)`,
  `view_test_cases()`, `finish()`). El docstring de cada método ES el
  prompt/descripción de esa acción. El harness introspecciona la clase con
  `inspect` y construye una descripción textual de la interfaz a partir de
  las firmas + docstrings (NO un schema JSON). El modelo responde indicando
  el método a llamar y sus argumentos en texto plano; el harness lo parsea y
  despacha al método real del objeto. NOOA es *backend-agnostic*: funciona
  con completions planos, sin depender del tool-use nativo del modelo.
- **Clásico (`classic_tools.py`):** las mismas acciones se definen como
  herramientas con schema JSON (formato `tools` de Claude y `functions` de
  OpenAI) y se invocan mediante el API de tool-calling *nativo* del backend. Las
  llamadas se despachan a las mismas acciones subyacentes que NOOA, de forma
  que ambos enfoques resuelvan la tarea idéntica.
- Ambos reusan el **mismo checker** (tests deterministas de brackets en
  subproceso aislado, copiado a `checker.py` para que el experimento sea
  autocontenido) y los **mismos frenos** (ver abajo), implementados una
  sola vez en un módulo compartido `brakes.py`.
- Se incluye un **backend mock** que devuelve respuestas programadas, para
  validar todo el loop *offline* sin claves de API ni modelo local.

**Frenos a reusar (un solo módulo compartido `brakes.py`):**
- Step cap → 10 iteraciones (ambos enfoques).
- Circuit breaker → 3 errores idénticos seguidos (ambos enfoques).
- Heartbeat → `loop_state.json` actualizado cada iteración (ambos enfoques).
- Budget ceiling → $0.10 USD (SOLO backend Claude; no existe en el código de
  los backends local/mock, igual que en el experimento 01).

**Métricas a capturar por ejecución:**
`success` (bool), `iterations` (pasos; = `steps` del marco), `stop_reason`
(`success` | `step_cap` | `circuit_breaker` | `budget`), `wall_time_s`,
`input_tokens`, `output_tokens`, `cost_usd` (solo Claude). Resultados a
`results/{approach}_runs.json` (append, igual que el experimento 01).

**Archivos a generar (espejo del experimento 01 + núcleo compartido):**
- `README.md` — setup, cómo ejecutar, qué mide, tabla de métricas, frenos,
  explicación NOOA vs. clásico, tabla + gráfico de comparación, limitaciones.
- `loop.py` — harness CLI: `--approach {nooa,classic}`, `--backend
  {local,claude,mock}`, `--runs N`, `--max-iters`, `--budget-usd`.
- `nooa_agent.py` — el agente-objeto + introspección + parseo/despacho.
- `classic_tools.py` — definición de tools (JSON schema) + despacho nativo.
- `checker.py` — `TEST_CASES` + `run_tests()` (subproceso aislado), compartido.
- `brakes.py` — frenos compartidos (step cap, circuit breaker, heartbeat,
  budget ceiling Claude-only) en un solo módulo.
- `plot.py` — gráfico NOOA vs. clásico → `results/comparacion.png`.
- `run_comparison.sh` — lanza N ejecuciones de cada enfoque en los backends
  disponibles y regenera el gráfico (salta backends sin credenciales, como el
  experimento 01 salta Claude sin `ANTHROPIC_API_KEY`).
- `skills/balanced_brackets/SKILL.md` — reusar la skill del experimento 01.
- `tests/` — unit tests pytest de las piezas offline (introspección NOOA,
  parseo/despacho, checker pass/fail incl. `"([)]"`, circuit breaker, run
  mock end-to-end).
- `results/` — `{approach}_runs.json`, `loop_state.json`, `comparacion.png`.

**Comparación NOOA vs. clásico:** ¿cambia la tasa de éxito, los pasos o el
costo de tokens según la arquitectura del agente, con tarea/checker/frenos
idénticos? Hipótesis: el tool-calling nativo puede ser más robusto de
formato (el modelo está entrenado para respetar el schema); NOOA puede ser
más portable (un solo prompt sirve para cualquier backend) a costa de
depender de que el modelo respete un formato textual acordado.

**Nota sobre credenciales (importante para la ejecución en este contenedor):**
este contenedor no tiene `ANTHROPIC_API_KEY` ni modelo local en
`localhost:4000`, así que los resultados reales NO se pueden producir aquí.
El harness se valida *offline* con el backend mock (smoke test end-to-end)
como evidencia de que funciona; los números reales requieren credenciales o
un modelo local, y el README documenta las instrucciones exactas para
reproducirlos. No se inventan números de modelo.

---

### 03 — Evals: el "checker" que le faltó al loop
**Estado:** 🔲 pendiente
**Carpeta destino:** `experiments/03-evals-agentes/`

**Por qué ahora:** evaluación y confiabilidad son señaladas como la parte
más difícil y más duradera del stack agentic en 2026 — la habilidad que no
se va a commoditizar tan rápido como "saber usar un framework".

**Objetivo didáctico:** mostrar que "funciona en mi demo" y "está evaluado"
son cosas distintas, y construir el puente entre ambas.

**Diseño concreto:**
- Definir una rúbrica de evaluación con criterios explícitos (no solo
  pass/fail binario): corrección, seguir instrucciones, manejo de casos
  límite, formato de salida.
- Set de 10-15 casos de prueba para una tarea fija (puede reusar/extender
  la del experimento 01, o ser una tarea ligeramente menos trivial).
- Un "juez" automatizado: puede ser determinista (asserts) donde se pueda,
  y un modelo evaluador separado (idealmente distinto del que generó la
  respuesta) donde no haya verificación objetiva posible — este es el
  primer lugar del lab donde de verdad hace falta un sub-agente checker,
  a diferencia del experimento 01.
- Correr la misma rúbrica contra Claude y contra Qwen local, varias veces,
  y reportar no solo el score promedio sino la varianza entre ejecuciones
  (¿es consistente o varía mucho run a run?).

**Comparación Claude vs. local:** ¿quién es más consistente entre ejecuciones,
no solo quién saca mejor score promedio? La varianza es tan interesante
como la media.

**Entregables:** mismo patrón que el experimento 01 (README propio, código,
`results/`, gráfico comparativo). Además: el harness de evals debería
quedar reusable para evaluar experimentos futuros del lab, no solo este.

---

### 04 — AI security / red-teaming de agentes
**Estado:** 🔲 pendiente
**Carpeta destino:** `experiments/04-ai-security-redteam/`

**Por qué ahora:** las plataformas de seguridad en IA están entre las
áreas de inversión prioritarias en 2026 (Gartner), justo cuando los
agentes empiezan a tener acceso real a herramientas y no solo a responder
texto.

**Objetivo didáctico:** mostrar de forma práctica cómo se ve un ataque de
prompt injection contra un agente con herramientas, y qué defensas
funcionan y cuáles no — formato "ataqué mi propio agente".

**Diseño concreto:**
- Un agente trivial con UNA herramienta simulada (ej. "enviar email",
  "leer archivo") que el agente puede invocar.
- Un set de prompts/inputs de injection conocidos (ej. instrucciones
  ocultas en contenido que el agente "lee" de una fuente externa
  simulada, intentando hacer que ignore su instrucción original o invoque
  la herramienta de forma no autorizada).
- Medir tasa de éxito del ataque, SIN documentar técnicas de ataque nuevas
  ni cómo evadir filtros reales — el foco es la defensa y el patrón, no un
  manual de ataque. Mantenerlo a nivel de patrones conocidos y públicos.
- Probar 2-3 capas de defensa (ej. delimitar claramente instrucción vs.
  contenido externo, validar la herramienta invocada contra una lista
  permitida, pedir confirmación explícita para acciones sensibles) y medir
  cuánto reduce cada una la tasa de éxito del ataque.

**Comparación Claude vs. local:** ¿qué tan vulnerable es cada uno antes y
después de cada capa de defensa? Es probable que la diferencia entre
modelos sea más marcada aquí que en el experimento 01.

**Nota importante para cuando se ejecute:** este experimento debe quedar
enmarcado explícitamente como educativo/defensivo, documentando patrones
conocidos y públicos de ataque-defensa, no produciendo técnicas nuevas de
explotación.

---

### 05 — Context engineering / "context rot"
**Estado:** 🔲 pendiente
**Carpeta destino:** `experiments/05-context-engineering/`

**Por qué ahora:** se está señalando como un diferenciador por encima del
prompt engineering en sistemas multiagente — qué información le das al
agente y cómo la mantienes manejable a medida que crece la conversación.

**Objetivo didáctico:** demostrar EMPÍRICAMENTE (con datos, no solo
afirmarlo) que el rendimiento de un agente se degrada cuando su contexto
se llena de historial y definiciones de herramientas — y qué mitigaciones
funcionan.

**Diseño concreto:**
- Una tarea fija con verificación objetiva (similar a los experimentos
  anteriores).
- Ir "rellenando" artificialmente el contexto antes de la tarea real (con
  historial irrelevante, definiciones de herramientas no usadas, ruido de
  distinto tipo) en pasos crecientes, y medir precisión/iteraciones-hasta-
  éxito en cada nivel de relleno.
- Probar al menos una mitigación (ej. resumir el historial antes de cada
  turno, o recuperar solo lo relevante en vez de mandar todo) y medir si
  recupera el rendimiento perdido.

**Comparación Claude vs. local:** ¿a partir de qué nivel de relleno cada
uno empieza a degradarse, y qué tan bien responde cada uno a la
mitigación? Es probable que la ventana de contexto efectiva (no la
nominal) sea distinta entre ambos.

---

### 06 — MCP server propio + A2A desde cero
**Estado:** 🔲 pendiente
**Carpeta destino:** `experiments/06-mcp-a2a-desde-cero/`

**Por qué ahora:** es de lo más nuevo en estandarización de
infraestructura agentic ahora mismo — construirlo desde cero (no solo
consumir un MCP server de terceros) da una comprensión que ningún tutorial
de "cómo conectar Notion vía MCP" da.

**Objetivo didáctico:** entender el protocolo por dentro construyendo la
pieza más simple posible de cada lado, en vez de tratarlo como una caja
negra.

**Diseño concreto:**
- Un servidor MCP propio, minimalista, que exponga UNA herramienta real y
  simple (ej. consultar un dataset local, o el propio `loop_state.json`
  de experimentos anteriores del lab — cerrando el círculo con lo ya
  hecho).
- Dos agentes hablando entre sí vía A2A: un orquestador que recibe la
  tarea y un especialista que la ejecuta usando el MCP server propio.
- Documentar el protocolo de mensajes real entre ambos (no solo el
  resultado final) — esa es la parte didáctica: mostrar la conversación
  agente-a-agente, no solo la respuesta.

**Comparación Claude vs. local:** ¿qué tan bien sigue cada uno el
protocolo de turnos sin salirse del formato esperado? Aquí la métrica
interesante no es "quién da mejor respuesta" sino "quién respeta mejor el
protocolo de comunicación entre agentes".

---

## Ideas futuras sin desarrollar (parking lot)

Anotar aquí cualquier idea que surja a mitad de un experimento y no
queramos perder, sin desarrollarla todavía. Cuando se vaya a ejecutar, se
le da el mismo nivel de detalle que a las de arriba antes de empezar.

-

---

## Cómo usar esta bitácora (para Claude Code)

1. Antes de empezar un experimento nuevo, lee esta bitácora completa y el
   README raíz del repo.
2. Confirma con el usuario el experimento a abrir si no está explícito en
   la instrucción de la sesión.
3. Si la sección del experimento no tiene suficiente detalle para
   ejecutar directamente (es un resumen, no un brief completo), primero
   expándela en esta misma bitácora con el mismo nivel de detalle que se
   usó para el experimento 01 (estructura de carpetas, qué métricas
   capturar, qué archivos genera) ANTES de escribir código.
4. Al terminar, cambia el estado a `✅ hecho`, agrega el link a la carpeta
   de resultados, y mueve cualquier aprendizaje relevante a
   `docs/loop-engineering-explicado.md` si aplica al marco conceptual
   general del lab (no solo a ese experimento puntual).
5. Comitea la actualización de la bitácora en un commit separado del
   código del experimento.
