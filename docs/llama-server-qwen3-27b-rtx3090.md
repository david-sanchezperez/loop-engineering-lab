# llama-server para Qwen3-27B (Q4_K_M) en RTX 3090

> Receta de referencia para servir el modelo local Qwen3-27B cuantizado en
> Q4_K_M con `llama-server` (llama.cpp) en una RTX 3090 (24 GB) y conectarlo
> al stack local del lab vía LiteLLM.

## Por qué existe este documento

El backend `local` del experimento 01 (`experiments/01-brackets/loop.py`)
habla con LiteLLM en `http://localhost:4000/v1` usando el modelo `qwen3` y la
clave `sk-litellm-local`. Este documento fija la receta exacta para levantar
esa pieza con `llama-server` en una RTX 3090: cuántas capas van a GPU, flash
attention y la plantilla Jinja de chat. Es documentación de infraestructura,
no un experimento nuevo.

## Requisitos previos

- **llama.cpp compilado con CUDA** (`llama-server` y `llama-bench` en el PATH).
- **RTX 3090**: 24 GB VRAM, Ampere (compute capability 8.6), ~936 GB/s.
- **GGUF Q4_K_M** del modelo descargado. El nombre exacto del archivo depende
  del repositorio de origen; ajusta `--model` a la ruta real de tu descarga.
- **LiteLLM** instalado (`pip install litellm[proxy]`).

## Receta completa

```bash
llama-server \
  --model /models/Qwen3-27B-Q4_K_M.gguf \
  --host 0.0.0.0 \
  --port 8080 \
  --n-gpu-layers -1 \
  --ctx-size 8192 \
  --flash-attn \
  --jinja \
  --threads 8 \
  --parallel 1
```

> Los flags de plantilla y atención varían entre versiones de llama.cpp.
> Comprueba siempre `llama-server --help` antes de arrancar y ajusta si tu
> build usa un alias distinto.

## Parámetros, con precisión

| Flag | Valor | Por qué |
|------|-------|---------|
| `--model` | `/models/Qwen3-27B-Q4_K_M.gguf` | Ruta del GGUF cuantizado en Q4_K_M |
| `--host` / `--port` | `0.0.0.0` / `8080` | Expone la API compatible con OpenAI de `llama-server` |
| `--n-gpu-layers` | `-1` | Todas las capas en GPU (ver sección siguiente) |
| `--ctx-size` | `8192` | Ventana de contexto; súbelo a `32768` si sobra VRAM (cuesta más KV cache) |
| `--flash-attn` | activo | Flash attention: menos pico de VRAM y prefill más rápido |
| `--jinja` | activo | Renderiza la plantilla Jinja de chat embebida en el GGUF |
| `--threads` | `8` | Hilos de CPU para el procesamiento residual del prompt |
| `--parallel` | `1` | Un solo slot de generación; suficiente para el lab mono-usuario |

### Capas en GPU (`--n-gpu-layers`)

- Un 27B en Q4_K_M pesa **~17 GB** de pesos. Con 24 GB de VRAM caben **todas
  las capas**: usa `-ngl -1` (o `-ngl 999`).
- Regla de decisión: offload total siempre que
  `peso_del_modelo + KV_cache + activaciones < VRAM_total`. Aquí se cumple
  con holgura para contexto de 8K.
- Si faltara VRAM (modelo mayor o contexto muy largo), baja `-ngl` a un número
  concreto (p. ej. `20`, `24`, `28`) para dejar las últimas capas en CPU a
  cambio de velocidad.
- Al arrancar, `llama-server` imprime el número de capas en GPU y el uso de
  VRAM: verifica que `n_gpu_layers` sea el esperado y que no haya fallback a CPU.

### Flash attention (`--flash-attn`)

- Activa el kernel de flash attention de llama.cpp: reduce el pico de memoria
  durante la atención y acelera el prefill, sobre todo con contexto largo.
- Requiere build CUDA en Ampere+ (compute capability 8.0+). La RTX 3090 es 8.6,
  así que es compatible.
- Si tu build usa Vulkan o Metal, verifica que el flag esté disponible en tu
  versión.

### Plantilla Jinja (`--jinja`)

- Los GGUF publicados en Hugging Face (p. ej. los quants de bartowski) llevan
  la plantilla de chat embebida en el campo `tokenizer.chat_template` del
  metadato. `llama-server` la lee automáticamente y `--jinja` la renderiza.
- Qwen3 usa formato ChatML (`<|im_start|>` / `<|im_end|>`) y separa el
  **thinking** (`reasoning_content`) de la **respuesta final** (`content`).
  Su plantilla envuelve el thinking en un bloque aparte con marcadores tipo
  `<|im_start|>think ... <|im_end|>`; `llama-server` lo expone como
  `reasoning_content` en la API compatible con OpenAI.
- Esto es justo lo que `loop.py` espera: `_call_local` lee
  `resp.choices[0].message.content` (el contenido final), mientras que el
  thinking de Qwen3 queda separado.
- Para usar una plantilla propia en vez de la embebida:
  `--chat-template-file ./qwen3.jinja`.

## Integración con LiteLLM (stack local)

LiteLLM expone el modelo `qwen3` sobre la API de `llama-server` y los clientes
del lab siguen hablando con `http://localhost:4000/v1` sin cambios.

```yaml
# litellm.config.yaml
general_settings:
  master_key: sk-litellm-local   # coincide con LOCAL_API_KEY de loop.py

model_list:
  - model_name: qwen3
    litellm_params:
      model: openai/qwen3
      api_base: http://localhost:8080/v1   # llama-server
      api_key: sk-dummy                    # llama-server no exige clave
```

Arranque del proxy:

```bash
litellm --config litellm.config.yaml --port 4000
```

Verificación de que el stack quedó conectado:

```bash
curl -s http://localhost:4000/v1/models \
  -H "Authorization: Bearer sk-litellm-local"
```

Y después, el backend local del experimento 01 sin ningún cambio:

```bash
cd experiments/01-brackets
python3 loop.py --backend local --runs 1 --max-iters 3
```

## Rendimiento: trabajo futuro explícito

Medir el rendimiento real (tokens/s de prefill y generación, pico de VRAM)
requiere descargar el GGUF (~17 GB) y ejecutar benchmarks que tardan más de
unos minutos. **No se ejecuta aquí**: se documenta el comando con precisión y
se deja la medición como trabajo futuro.

```bash
# Benchmark pendiente de ejecutar (trabajo futuro)
llama-bench -m /models/Qwen3-27B-Q4_K_M.gguf -ngl -1 -fa -c 8192
```

Cuando se ejecute, registrar en los resultados: `pp512` (prefill), `tg128`
(generación), VRAM máxima y temperatura/estabilidad térmica de la 3090.
