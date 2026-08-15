# llama-server para Qwen3.8-27B (Q4_K_M) en RTX 3090

> Configuración de referencia para servir el modelo local del lab con
> `llama-server` (llama.cpp). Documenta el comando, la elección de cada
> parámetro y el presupuesto de VRAM en una RTX 3090 de 24 GB.

**Nota de nomenclatura:** en la descripción de la tarea el modelo figura como
"Qwen3-27B". Su nombre real en Hugging Face es **Qwen3.8-27B**
([`Qwen/Qwen3.8-27B`](https://huggingface.co/Qwen/Qwen3.8-27B)), un modelo
multimodal con modo *thinking* lanzado en agosto de 2026. Este documento usa el
nombre real y la cuantización **Q4_K_M**.

---

## Contexto

El stack local del lab (ver `experiments/01-brackets/`) consume un modelo Qwen
local a través de LiteLLM en `localhost:4000`, que a su vez reenvía a un
servidor OpenAI-compatible. Este documento fija cómo levantar ese servidor con
`llama-server` para una **RTX 3090 (24 GB, Ampere / SM 8.6)**.

| Dato | Valor |
|------|-------|
| Modelo | `Qwen/Qwen3.8-27B` |
| GGUF | `unsloth/Qwen3.8-27B-GGUF` → `Qwen3.8-27B-Q4_K_M.gguf` (~17.1 GB) |
| Arquitectura | `qwen35`: 64 capas — 16 full-attention + 48 linear-attention (híbrida) |
| Contexto nominal | 262 144 tokens |
| Hardware objetivo | RTX 3090, 24 GB VRAM, CUDA (Ampere) |

La arquitectura es híbrida: solo 16 de las 64 capas son de atención completa
(las que acumulan KV cache); las otras 48 son de atención lineal y mantienen un
estado recurrente de tamaño fijo que **no crece con el contexto**. Esto hace
que el KV cache de este modelo sea mucho más barato que el de un transformer
denso del mismo tamaño.

---

## Requisitos

- **llama.cpp reciente** con soporte CUDA. La arquitectura `qwen35` y el
  template multimodal + thinking requieren una build de 2026 (verificado contra
  `b10435`). El binario es `llama-server` (antes `server`).
- RTX 3090 con driver CUDA funcional (`nvidia-smi`).

---

## Descargar el modelo

```bash
mkdir -p ~/models
curl -L -o ~/models/Qwen3.8-27B-Q4_K_M.gguf \
  "https://huggingface.co/unsloth/Qwen3.8-27B-GGUF/resolve/main/Qwen3.8-27B-Q4_K_M.gguf"
```

---

## El comando

```bash
llama-server \
  --model ~/models/Qwen3.8-27B-Q4_K_M.gguf \
  --host 127.0.0.1 \
  --port 8080 \
  --n-gpu-layers all \
  --flash-attn on \
  --jinja \
  --ctx-size 32768 \
  --cache-type-k q8_0 \
  --cache-type-v q8_0 \
  --parallel 1
```

Este es el punto de partida para el lab. Las secciones siguientes explican por
qué cada flag tiene ese valor y qué cambiar si el entorno difiere.

---

## Por qué cada parámetro

### `--n-gpu-layers all`

Descarga las 64 capas a la GPU. El Q4_K_M ocupa ~17.1 GB, así que cabe entero
en los 24 GB de la 3090 y **ninguna capa debería ejecutarse en CPU** (eso
mataría la velocidad de generación).

- `all` es equivalente a `-ngl 64` para este modelo.
- Si no cabe (otra carga en la GPU), reduce contexto o baja el número exacto de
  capas (`-ngl 60`, etc.) y acepta la penalización de velocidad.

### `--flash-attn on`

Activa Flash Attention. Ampere (SM 8.6) lo soporta de forma nativa. Ventajas:

- **Menos VRAM de cómputo:** no materializa la matriz de atención completa, lo
  que importa en prefill con contexto largo.
- **Prefill más rápido** con `--ctx-size` grande.

No reduce el KV cache en sí; eso lo hace `--cache-type-*`. El default es `auto`
(que en Ampere normalmente ya lo activa); fijarlo en `on` lo hace explícito y
reproducible.

### `--jinja`

Usa el **template Jinja embebido en el GGUF**. Es crítico para Qwen3.8 porque el
template maneja:

- el formato multimodal (tokens `<|vision_start|>…<|vision_end|>`),
- el modo thinking (`enable_thinking`, `reasoning_content`, `<think>…</think>`).

Sin `--jinja`, llama.cpp solo acepta un conjunto de templates "comunes" que no
reproducen el formato de Qwen3.8 y rompen el modo thinking. Con `--jinja`, el
template correcto sale de los metadatos del propio modelo.

Si hiciera falta anularlo (p. ej. para un formato propio), se usa
`--chat-template-file plantilla.jinja` **después** de `--jinja`.

### `--ctx-size 32768`

Tamaño de contexto de trabajo. 32k cubre de sobra los loops del lab (los prompts
del experimento 01 son de cientos de tokens) y deja margen para historial largo.

El modelo admite nominalmente 256k, pero en 24 GB el límite real lo pone el KV
cache (ver sección siguiente). Con `q8_0` se puede subir a 128k sin problemas;
256k requeriría cuantizar más el KV cache (`q4_0`) o dejar capas en CPU.

### `--cache-type-k q8_0` / `--cache-type-v q8_0`

Cuantiza el KV cache a 8 bits. `q8_0` es prácticamente indistinguible de `f16`
en calidad y **reduce a la mitad** la VRAM por token. Valores permitidos por
llama.cpp actual: `f32`, `f16`, `bf16`, `q8_0`, `q4_0`, `q4_1`, `iq4_nl`,
`q5_0`, `q5_1`.

Solo las 16 capas full-attention acumulan KV cache. Por token:

- 16 capas × 4 cabezas KV × 256 de head_dim × 2 (K+V) = **32 768 elementos**.

| Tipo de KV cache | Bytes/token | 32k ctx | 128k ctx |
|------------------|-------------|---------|----------|
| `f16` | ~64 KB | ~2.1 GB | ~8.6 GB ❌ |
| `q8_0` | ~34 KB | ~1.1 GB | ~4.6 GB ✅ |
| `q4_0` | ~18 KB | ~0.6 GB | ~2.3 GB ✅ |

### `--parallel 1`

Un único slot de servidor. Cada slot extra multiplica el KV cache y el estado
recurrente de las capas lineales; con un solo agente local no hace falta más.
El default es `auto`; fijar `1` hace el consumo de VRAM predecible.

---

## Presupuesto de VRAM

| Componente | Tamaño aprox. |
|------------|---------------|
| Pesos `Q4_K_M` | ~17.1 GB |
| Contexto CUDA + buffers de cómputo | ~0.8–1.5 GB |
| **Disponible para KV cache** | **~5.5–6 GB** |

Con `--ctx-size 32768 --cache-type-k/v q8_0`, el KV cache ocupa ~1.1 GB y el
total queda en ~19–20 GB: holgura suficiente para que la GPU no haga swapping.
Las capas de atención lineal añaden un estado recurrente fijo por secuencia
(del orden de decenas/cientos de MB, no crece con el contexto).

> Cifras aproximadas: dependen de la build, el driver y los buffers de cómputo.
> Verifica el consumo real con `nvidia-smi` tras arrancar (ver más abajo).

---

## Verificación

### Salud del servidor

```bash
curl http://127.0.0.1:8080/health
# {"status":"ok"}  ← esperado
```

### Petición OpenAI-compatible

```bash
curl http://127.0.0.1:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3.8-27b",
    "messages": [{"role": "user", "content": "Responde en una frase: ¿2+2?"}],
    "max_tokens": 128
  }'
```

`llama-server` sirve un único modelo cargado, así que el valor de `"model"` es
informativo en esta petición directa (LiteLLM lo usa para enrutar; ver la
sección [Integración con LiteLLM](#integración-con-litellm-proxy)).

### Consumo real de VRAM

```bash
nvidia-smi
# revisa la columna "Memory-Usage" del proceso llama-server
```

En el arranque, `llama-server` imprime el presupuesto calculado
(`n_gpu_layers`, `KV self size`, etc.). Si el total se acerca a los 24 GB,
baja `--ctx-size` o pasa el KV cache a `q4_0`.

Para una medición automatizada (TTFT, tokens/s y pico de VRAM) usa
[`bench_llama.py`](bench_llama.py) — ver [Medición de rendimiento](#medición-de-rendimiento).

---

## Medición de rendimiento

Para validar que la configuración rinde como se espera,
[`bench_llama.py`](bench_llama.py) de esta carpeta mide contra el endpoint
OpenAI-compatible:

- **time-to-first-token (TTFT)** — latencia hasta el primer token (incluye el
  modo thinking si está activo);
- **tokens/s de generación** — velocidad de decodificación (excluye el TTFT);
- **tokens/s totales** — incluyendo el TTFT (lo que percibe el cliente);
- **uso de VRAM** (con `--vram`) — pico de memoria vía `nvidia-smi` durante la
  corrida.

```bash
# contra llama-server directo (valida la config de llama-server)
python3 bench_llama.py

# a través de LiteLLM (valida la integración del lab — sección siguiente)
python3 bench_llama.py \
  --base-url http://localhost:4000/v1 \
  --api-key sk-litellm-local \
  --model qwen3

# corrida más larga, con muestreo de VRAM
python3 bench_llama.py --runs 5 --max-tokens 512 --vram
```

Cada corrida se guarda en `results/bench.json` (los registros se acumulan).

### Cómo leer los resultados

| Métrica | Qué mide | Esperado en RTX 3090 (orientativo) |
|---------|----------|------------------------------------|
| `ttft_s` | Latencia al primer token | < 1 s para prompts cortos; más si el modo thinking está activo (el primer token puede ser de reasoning) |
| `gen_tokens_per_s` | Velocidad de decodificación | ~20–45 tok/s con Q4_K_M y 64 capas en GPU; < 5 tok/s sugiere capas cayendo a CPU |
| `total_tokens_per_s` | Velocidad total (incluye TTFT) | Menor que `gen_tokens_per_s`; se acerca a ella con `max_tokens` grandes |
| `vram_peak.used_mib` | Pico de VRAM | ~19–20 GiB con `--ctx-size 32768` y KV `q8_0`; cerca de 24 GiB hay riesgo de OOM |

Notas:

- La primera petición tras arrancar puede ser más lenta (warm-up del contexto
  CUDA y de los buffers); las siguientes son las representativas.
- Si el modo thinking está activo, el primer token suele ser de `reasoning`;
  la velocidad de *contenido* útil se mide con `gen_tokens_per_s`.
- El TTFT no incluye el tiempo de carga del modelo: mide con el servidor ya
  arriba (sección [Verificación](#verificación)).

---

## Integración con LiteLLM proxy

El stack local del lab (ver `experiments/01-brackets/loop.py`) no habla directo
con `llama-server`: habla con **LiteLLM** en `localhost:4000`, que a su vez
reenvía a `llama-server` en `localhost:8080`. LiteLLM es el conector que le da
una única URL OpenAI-compatible al agente, con un nombre de modelo estable
(`qwen3`) independiente de qué servidor de inferencia haya detrás.

| Pieza | Valor | Dónde está definido |
|-------|-------|---------------------|
| URL del cliente | `http://localhost:4000/v1` | `LOCAL_BASE_URL` en `loop.py` |
| API key del cliente | `sk-litellm-local` | `LOCAL_API_KEY` en `loop.py` |
| Modelo que pide el cliente | `qwen3` | `LOCAL_MODEL` en `loop.py` |
| Modelo que sirve `llama-server` | `openai/qwen3.8-27b` en `127.0.0.1:8080` | `litellm-config.yaml` |

### El config

El archivo [`litellm-config.yaml`](litellm-config.yaml) de esta carpeta ya deja
todo listo. Las dos piezas clave:

- `model_list[0].model_name: qwen3` — el nombre público que el cliente usa.
- `model_list[0].litellm_params` — apunta a `http://127.0.0.1:8080/v1` con el
  prefijo `openai/` (ruta OpenAI-compatible). `llama-server` sirve un único
  modelo cargado, así que el nombre que viaja aguas abajo
  (`qwen3.8-27b`) es informativo: el enrutamiento lo decide `model_name`.
- `general_settings.master_key: sk-litellm-local` — la clave que el cliente
  manda como `Authorization: Bearer ...`. Sin esta línea, LiteLLM genera una
  clave aleatoria al arrancar y el lab no se autentica.

### Levantar el proxy

Con `llama-server` ya corriendo (sección [El comando](#el-comando)):

```bash
pip install 'litellm[proxy]'
litellm --config docs/llama-server-qwen3-27b/litellm-config.yaml --port 4000
```

LiteLLM escucha en `localhost:4000`. Para verificarlo:

```bash
# salud del proxy
curl http://localhost:4000/health/liveliness

# petición de extremo a extremo (cliente → LiteLLM → llama-server)
curl http://localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer sk-litellm-local" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3",
    "messages": [{"role": "user", "content": "Responde en una frase: ¿2+2?"}],
    "max_tokens": 128
  }'
```

Si la respuesta llega, la integración está lista: el experimento 01 ya puede
correr con `python3 loop.py --backend local --runs 5` sin tocar nada más.

### Notas

- **Thinking y `reasoning_content`:** con `--reasoning-format deepseek` en
  `llama-server`, el thinking viaja en el campo `message.reasoning_content`,
  separado de `content` (que es lo que el lab consume). Si una versión de
  LiteLLM no reenvía ese campo, usa el formato por defecto de `llama-server`
  (thinking dentro de `content`) o actualiza LiteLLM.
- **Una sola key, un solo host:** el config usa la `master_key` directamente
  para simplificar. Para entornos multiusuario conviene crear *virtual keys*
  con `litellm` en vez de repartir la clave maestra.

---

## Ajuste fino (opcional)

Flags que no están en el comando base pero conviene conocer:

| Flag | Qué hace | Cuándo usarlo |
|------|----------|---------------|
| `--threads N` | Hilos de CPU para generación | Con capas en CPU; con `-ngl all` apenas importa |
| `--batch-size N` / `--ubatch-size N` | Lote lógico / físico del prefill | Prefill más rápido con contexto largo; más VRAM de cómputo |
| `--reasoning-budget N` | Tope de tokens de thinking (`-1` ilimitado) | Para acotar latencia del modo thinking en el lab |
| `--reasoning-effort LEVEL` | Esfuerzo de reasoning (`minimal`…`max`) | Ajustar thinking sin tocar el template |
| `--reasoning on\|off` | Activa/desactiva thinking (default `auto`) | Para tareas que no lo necesitan (menos latencia) |
| `--reasoning-format deepseek` | Devuelve el thinking en `message.reasoning_content`, separado de `content` | Para que el cliente OpenAI-compatible reciba el thinking aparte (como ya espera el lab) |
| `--load-mode mlock` | Evita que el SO swapee/compacte el modelo | Si la VRAM se pagea y aparecen pausas |

---

## Problemas comunes

| Síntoma | Causa probable | Solución |
|---------|----------------|----------|
| `CUDA error: out of memory` al arrancar | KV cache + pesos no caben | Baja `--ctx-size`, o `-ctk/-ctv q4_0`, o `-ngl` con capas en CPU |
| Respuestas con formato roto / sin thinking | Template no aplicado | Asegura `--jinja` (y que la build soporte `qwen35`) |
| Error `unknown architecture 'qwen35'` | Build de llama.cpp vieja | Recompila/actualiza a una build de 2026 |
| Generación lenta a pesar de `-ngl all` | Capas cayendo a CPU o GPU en P-state bajo | Verifica `nvidia-smi` y `llama-server` log; prueba `--load-mode mlock` |
