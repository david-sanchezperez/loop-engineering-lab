# Loop Engineering: la guía completa

> "No basta con darle un prompt mejor a un modelo. Tienes que diseñar el sistema
> que lo rodea." — definición de trabajo

---

## Qué es loop engineering

Loop engineering es **diseñar el sistema que rodea a un agente**, no solo el
prompt que se le da.

Tiene dos mitades que no se pueden separar:

**Mitad 1 — el motor:** hacer que el agente actúe sobre algo real, observe el
resultado real, y decida solo cuándo parar.

**Mitad 2 — los frenos:** limitar explícitamente cuánto daño puede hacer el
agente mientras nadie lo está mirando.

Un agente sin motor es un chatbot. Un agente sin frenos es un sistema que
puede iterar hasta el infinito, gastar dinero ilimitado, o romper cosas sin
que nadie lo note. Loop engineering es el arte de tener ambas mitades a la vez.

---

## Las 6 piezas

### 1. Estado persistente

El loop necesita saber dónde está en cada momento. Sin estado persistente,
si el proceso cae, todo lo aprendido se pierde y hay que empezar de cero.

**En este repo:** cada iteración escribe `results/loop_state.json` con el
backend, el número de corrida, la iteración actual, el estado (`running` /
`success` / `circuit_breaker`) y un timestamp UTC.

```python
# loop.py — función write_heartbeat
def write_heartbeat(state: dict) -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))
```

Si el proceso muere en medio de una corrida, `loop_state.json` tiene el
último estado conocido. En un sistema más sofisticado, este archivo permite
reanudar desde donde se quedó.

---

### 2. Automatización / cadencia

El loop no puede requerir intervención humana en cada iteración. Tiene que
poder avanzar solo, basándose en observaciones del mundo real.

**En este repo:** el harness en `loop.py` ejecuta un ciclo completo sin
esperar input del usuario. En cada iteración:
1. Llama al modelo
2. Extrae el código de la respuesta
3. Corre los tests
4. Decide si continuar o parar

```python
# loop.py — ciclo principal (backend local)
for iteration in range(1, max_iters + 1):
    response  = _call_local(messages)
    last_code = extract_code(response)
    success, error = run_tests(last_code)
    if success:
        stop_reason = "success"
        ...
        return result
    # continúa solo si falla
```

La cadencia aquí la marca la latencia del modelo (segundos a decenas de
segundos). En un sistema de producción podría ser un cron o un trigger
basado en eventos.

---

### 3. Aislamiento (blast radius)

El agente necesita poder actuar, pero sus errores no deben poder romper el
sistema externo. Hay que aislar el radio de explosión.

**En este repo:** los tests corren en un **subproceso aislado**. El código
generado por el modelo se escribe en un archivo temporal y se ejecuta con
`subprocess.run`. Si el código tiene errores de sintaxis, lanza excepciones,
o hace cosas raras, el daño está contenido en ese subproceso.

```python
# loop.py — función run_tests
def run_tests(code: str) -> tuple[bool, str]:
    script = _TEST_HARNESS_TEMPLATE.format(code=code, cases=TEST_CASES)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(script)
        tmp = f.name
    try:
        r = subprocess.run(
            [sys.executable, tmp],
            capture_output=True, text=True, timeout=10,
        )
```

En un sistema más complejo, el aislamiento puede ser un contenedor Docker,
una VM, o un entorno sandboxed. La pregunta siempre es: ¿cuánto daño puede
hacer el agente si genera código o acciones incorrectas?

---

### 4. Skills (intención escrita una vez, fuera del código)

Una skill es la especificación de lo que el agente tiene que hacer, escrita
en lenguaje natural, en un archivo separado del código. Esto permite cambiar
la tarea sin tocar el harness.

**En este repo:** `skills/balanced_brackets/SKILL.md` define exactamente qué
debe implementar el modelo: la firma de la función, las reglas, los casos de
prueba esperados.

```markdown
# Skill: is_balanced

def is_balanced(s: str) -> bool:
    """
    Retorna True si los brackets en `s` están correctamente balanceados.
    Brackets soportados: (), [], {}
    ...
    """
```

El harness simplemente lee este archivo como el prompt inicial:

```python
# loop.py
def build_initial_prompt() -> str:
    return SKILL_PATH.read_text()
```

Para crear el experimento 02, bastará con escribir una nueva skill y apuntar
el harness a ella. El motor no cambia.

---

### 5. Conectores (actuar sobre sistemas reales)

Un loop útil no solo genera texto — actúa sobre el mundo real. Los conectores
son las integraciones que permiten eso: APIs, bases de datos, sistemas de
archivos, servicios externos.

**En este repo:** el conector más importante es el **juez determinista** —
el subproceso que ejecuta código Python real y devuelve un resultado
verificable. No es el modelo evaluándose a sí mismo (eso no es confiable);
es Python real ejecutando código real.

```python
# loop.py — TEST_CASES son la fuente de verdad
TEST_CASES = [
    ...
    ("([)]", False),   # ← el caso que rompe soluciones naive por conteo
    ...
]
```

En sistemas de producción, estos conectores pueden ser herramientas MCP
(Model Context Protocol) que permiten al agente leer archivos, ejecutar
comandos, consultar bases de datos, o llamar APIs externas.

---

### 6. Sub-agentes maker/checker

Cuando el agente se autoevalúa, miente — no porque sea malicioso, sino porque
el modelo que genera la respuesta y el que la evalúa tienen los mismos sesgos
y puntos ciegos. La verificación objetiva requiere un evaluador independiente.

**En este repo:** el "maker" es el LLM (Qwen3 o Claude) que genera código.
El "checker" es el intérprete de Python corriendo los tests deterministas.
Son dos sistemas distintos con criterios de éxito independientes.

```python
# El maker genera código:
response  = _call_local(messages)
last_code = extract_code(response)

# El checker lo evalúa (no el modelo, sino Python):
success, error = run_tests(last_code)
```

La separación maker/checker es la diferencia entre un loop que converge y uno
que "parece" que funciona porque el modelo siempre dice que sí.

---

## Los 4 frenos

Un loop sin frenos es peligroso. Estos son los 4 que todo sistema necesita:

### 1. Step cap (`--max-iters`)

Límite duro en el número de iteraciones. Si el loop llega a este límite, para
y reporta `stop_reason: "step_cap"`.

```python
# loop.py
DEFAULT_MAX_ITERS = 10

for iteration in range(1, max_iters + 1):
    ...
    if iteration == max_iters:
        stop_reason = "step_cap"
        break
```

**Por qué es necesario:** sin este límite, un loop podría iterar indefinidamente
si el modelo sigue intentando pero nunca converge.

---

### 2. Circuit breaker

Si el mismo error se repite 3 veces seguidas, el loop para. No tiene sentido
seguir enviando el mismo error si el modelo no puede corregirlo.

```python
# loop.py
CIRCUIT_BREAKER_THRESHOLD = 3

if error == last_error:
    consecutive += 1
else:
    consecutive = 1
    last_error  = error

if consecutive >= CIRCUIT_BREAKER_THRESHOLD:
    stop_reason = "circuit_breaker"
    break
```

**Por qué es necesario:** evita el "paseo aleatorio" — el modo de falla donde
el modelo intenta cosas distintas pero ninguna funciona y el loop nunca converge.
El circuit breaker detecta el estancamiento por señal (error repetido) en vez
de esperar a que se agote el step cap.

---

### 3. Heartbeat

Cada iteración escribe su estado en `loop_state.json`. Si el proceso muere
o se cuelga, el estado queda registrado.

```python
# loop.py
def write_heartbeat(state: dict) -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))
```

**Por qué es necesario:** sin heartbeat, un loop colgado es invisible. Con
heartbeat, el timestamp de la última escritura te dice cuándo fue la última
actividad. Si el timestamp tiene 20 minutos de antigüedad y el loop debería
iterar cada 30 segundos, algo está mal.

---

### 4. Techo de presupuesto (solo donde hay costo real)

Un límite en gasto en USD. **Solo aplica al backend Claude** — no existe en
el backend local porque las llamadas locales no tienen costo por token.

```python
# loop.py — SOLO en run_loop_claude, este bloque no existe en run_loop_local
if total_cost >= budget_usd:
    stop_reason = "budget"
    break
```

**Por qué está separado:** el freno de presupuesto solo tiene sentido donde
hay dinero real en juego. En el backend local no hay costo, así que calcular
y comparar un "presupuesto" sería código muerto — y código muerto que simula
un freno real da una falsa sensación de seguridad.

---

## Los 4 modos de falla de un loop

### 1. Recursión descontrolada

El loop sigue indefinidamente porque no tiene step cap o el step cap es
demasiado alto. Gasta recursos (tiempo, dinero, tokens) sin límite.

**Síntoma:** el proceso corre "para siempre" o hasta que el servidor lo mata.

**Solución:** step cap duro, razonable para la tarea.

---

### 2. Muerte silenciosa

El loop para sin dejar rastro. No sabes si terminó bien, si falló, o si se
colgó a mitad. El estado queda indefinido.

**Síntoma:** el proceso no devuelve resultados pero tampoco reporta error.

**Solución:** heartbeat en cada iteración + logging explícito de `stop_reason`.

---

### 3. Paseo aleatorio

El loop sigue iterando pero no converge. El modelo genera respuestas distintas
en cada iteración pero ninguna pasa los tests. Sin circuit breaker, consume
todo el step cap sin progresar.

**Síntoma:** las iteraciones tienen errores distintos en cada paso, el porcentaje
de éxito no mejora con más intentos.

**Solución:** circuit breaker por error repetido + análisis de si el problema
es la tarea (demasiado difícil) o el feedback (error message no informativo).

---

### 4. Deuda de comprensión

El loop "funciona" en el sentido de que produce resultados, pero nadie entiende
por qué toma las decisiones que toma, cuándo para, o qué significa el output.
Esto crea dependencia frágil: si algo cambia, nadie sabe cómo arreglarlo.

**Síntoma:** el sistema está en producción pero nadie puede explicar qué haría
si el modelo empieza a fallar más.

**Solución:** skills como archivos de texto versionados, logging de `stop_reason`
en cada corrida, métricas acumuladas en JSON, documentación del harness.

---

## Este repo como ejemplo completo

El experimento 01 (`experiments/01-brackets/`) tiene las 6 piezas y los 4
frenos. Es trivial a propósito: la tarea (`is_balanced`) es simple pero tiene
el edge case `"([)]"` que rompe soluciones naive, forzando al menos una
iteración de corrección en modelos que usen conteo en vez de stack.

La utilidad del experimento no está en la tarea — está en **validar el harness**
antes de usarlo con tareas más complejas donde los errores cuestan más.

Los experimentos siguientes (`02-...`, `03-...`) pueden reutilizar el mismo
harness con distintas skills y tests, aumentando gradualmente la complejidad.
