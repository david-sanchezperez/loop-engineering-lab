#!/usr/bin/env python3
"""
loop.py — harness para el experimento 01: paréntesis balanceados

Tarea: implementar is_balanced(s) que detecta si los brackets (), [], {}
están correctamente anidados. El caso "([)]" es el que rompe soluciones
naive por conteo y fuerza que el modelo use un stack.

Backends soportados:
  local   → LiteLLM proxy (Qwen3 via llama.cpp), sin costo por token
  claude  → Anthropic API, con techo de presupuesto en USD

Frenos implementados:
  1. Step cap        → --max-iters (default: 10)
  2. Circuit breaker → mismo error 3 veces seguidas → para
  3. Heartbeat       → loop_state.json actualizado en cada iteración
  4. Budget ceiling  → SOLO backend claude (no existe en el código del backend local)
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import time
from datetime import datetime, timezone
from pathlib import Path

# ── configuración ────────────────────────────────────────────────────────────

LOCAL_BASE_URL = "http://localhost:4000/v1"
LOCAL_API_KEY  = "sk-litellm-local"
LOCAL_MODEL    = "qwen3"

CLAUDE_MODEL                  = "claude-haiku-4-5-20251001"
CLAUDE_INPUT_PRICE_PER_TOKEN  = 0.80 / 1_000_000   # USD / token
CLAUDE_OUTPUT_PRICE_PER_TOKEN = 4.00 / 1_000_000   # USD / token

CIRCUIT_BREAKER_THRESHOLD = 3
DEFAULT_MAX_ITERS         = 10
DEFAULT_BUDGET_USD        = 0.10   # solo se usa en backend claude

RESULTS_DIR = Path(__file__).parent / "results"
STATE_FILE  = RESULTS_DIR / "loop_state.json"
SKILL_PATH  = Path(__file__).parent / "skills" / "balanced_brackets" / "SKILL.md"

# ── prompt / skill ───────────────────────────────────────────────────────────

def build_initial_prompt() -> str:
    return SKILL_PATH.read_text()

def build_correction_prompt(code: str, error: str) -> str:
    return f"""El código que generaste falló en los tests con el siguiente error:

```
{error}
```

El código que generaste fue:
```python
{code}
```

Corrige la función. Devuelve SOLO la función `is_balanced` en un bloque ```python ... ```.
Sin imports, sin explicaciones, sin texto fuera del bloque de código."""

# ── extracción de código ─────────────────────────────────────────────────────

def extract_code(response: str) -> str:
    """Extrae el primer bloque ```python...``` de la respuesta del modelo."""
    m = re.search(r"```python\s*(.*?)```", response, re.DOTALL)
    if m:
        return m.group(1).strip()
    return response.strip()

# ── test determinista (el juez — no el modelo se autoevalúa) ─────────────────

TEST_CASES = [
    # vacío
    ("",        True),
    # pares simples
    ("()",      True),
    ("[]",      True),
    ("{}",      True),
    # secuencias
    ("()[]{}",  True),
    # anidados correctos
    ("([])",    True),
    ("{[()]}",  True),
    ("([{}])",  True),
    # mal anidados — este es el caso clave que rompe soluciones naive por conteo
    ("([)]",    False),
    # solo abiertos
    ("(",       False),
    ("[",       False),
    ("(()",     False),
    # solo cerrados
    (")",       False),
    ("]",       False),
    # cierre extra
    ("())",     False),
]

_TEST_HARNESS_TEMPLATE = textwrap.dedent("""\
    import sys

    {code}

    cases = {cases!r}
    errors = []
    for s, expected in cases:
        try:
            result = is_balanced(s)
        except Exception as e:
            errors.append(f"EXCEPTION en is_balanced({{s!r}}): {{e}}")
            continue
        if result != expected:
            errors.append(f"FAIL: is_balanced({{s!r}}) = {{result!r}}, esperado {{expected!r}}")

    if errors:
        print("\\n".join(errors))
        sys.exit(1)
    sys.exit(0)
""")

def run_tests(code: str) -> tuple[bool, str]:
    """Ejecuta los tests en subproceso aislado. Retorna (éxito, mensaje_error)."""
    if not code:
        return False, "El modelo no generó código (respuesta vacía o solo reasoning)"

    script = _TEST_HARNESS_TEMPLATE.format(code=code, cases=TEST_CASES)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(script)
        tmp = f.name
    try:
        r = subprocess.run(
            [sys.executable, tmp],
            capture_output=True, text=True, timeout=10,
            check=False,
        )
        if r.returncode == 0:
            return True, ""
        return False, (r.stdout + r.stderr).strip() or "Error desconocido (exit code != 0)"
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT: el script tardó más de 10 segundos"
    finally:
        os.unlink(tmp)

# ── heartbeat ────────────────────────────────────────────────────────────────

def write_heartbeat(state: dict) -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))

# ── backend local (LiteLLM / llama.cpp, sin costo) ───────────────────────────

def _call_local(messages: list[dict]) -> str:
    from openai import OpenAI
    client = OpenAI(base_url=LOCAL_BASE_URL, api_key=LOCAL_API_KEY)
    resp = client.chat.completions.create(
        model=LOCAL_MODEL,
        messages=messages,
        max_tokens=3000,   # Qwen3 thinking consume tokens antes del contenido real
    )
    return resp.choices[0].message.content or ""


def run_loop_local(max_iters: int, run_id: int) -> dict:
    start       = time.time()
    messages    = [{"role": "user", "content": build_initial_prompt()}]
    last_error  = None
    consecutive = 0
    last_code   = ""
    stop_reason = "unknown"
    iteration   = 0

    for iteration in range(1, max_iters + 1):
        write_heartbeat({
            "backend": "local", "run_id": run_id, "iteration": iteration,
            "status": "running", "ts": datetime.now(timezone.utc).isoformat(),
        })

        response  = _call_local(messages)
        last_code = extract_code(response)
        success, error = run_tests(last_code)

        if success:
            stop_reason = "success"
            write_heartbeat({
                "backend": "local", "run_id": run_id, "iteration": iteration,
                "status": "success", "ts": datetime.now(timezone.utc).isoformat(),
            })
            return {
                "backend": "local", "model": LOCAL_MODEL, "run_id": run_id,
                "success": True, "iterations": iteration, "stop_reason": stop_reason,
                "wall_time_s": round(time.time() - start, 2),
                "ts": datetime.now(timezone.utc).isoformat(),
            }

        # circuit breaker
        if error == last_error:
            consecutive += 1
        else:
            consecutive = 1
            last_error  = error

        if consecutive >= CIRCUIT_BREAKER_THRESHOLD:
            stop_reason = "circuit_breaker"
            break

        if iteration == max_iters:
            stop_reason = "step_cap"
            break

        messages.append({"role": "assistant", "content": response})
        messages.append({"role": "user", "content": build_correction_prompt(last_code, error)})

    write_heartbeat({
        "backend": "local", "run_id": run_id, "iteration": iteration,
        "status": stop_reason, "ts": datetime.now(timezone.utc).isoformat(),
    })
    return {
        "backend": "local", "model": LOCAL_MODEL, "run_id": run_id,
        "success": False, "iterations": iteration, "stop_reason": stop_reason,
        "wall_time_s": round(time.time() - start, 2),
        "ts": datetime.now(timezone.utc).isoformat(),
    }

# ── backend Claude (Anthropic API, con presupuesto) ───────────────────────────

def _call_claude(messages: list[dict]) -> tuple[str, int, int, float]:
    """Retorna (content, input_tokens, output_tokens, cost_usd)."""
    import anthropic

    client = anthropic.Anthropic()
    anthropic_msgs = [m for m in messages if m["role"] != "system"]

    resp = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        messages=anthropic_msgs,
    )
    content  = resp.content[0].text
    in_tok   = resp.usage.input_tokens
    out_tok  = resp.usage.output_tokens
    cost_usd = in_tok * CLAUDE_INPUT_PRICE_PER_TOKEN + out_tok * CLAUDE_OUTPUT_PRICE_PER_TOKEN
    return content, in_tok, out_tok, cost_usd


def run_loop_claude(max_iters: int, budget_usd: float, run_id: int) -> dict:
    start         = time.time()
    messages      = [{"role": "user", "content": build_initial_prompt()}]
    last_error    = None
    consecutive   = 0
    last_code     = ""
    stop_reason   = "unknown"
    total_in_tok  = 0
    total_out_tok = 0
    total_cost    = 0.0
    iteration     = 0

    for iteration in range(1, max_iters + 1):
        write_heartbeat({
            "backend": "claude", "run_id": run_id, "iteration": iteration,
            "status": "running", "cost_usd_so_far": round(total_cost, 6),
            "ts": datetime.now(timezone.utc).isoformat(),
        })

        # ── techo de presupuesto — ÚNICO lugar donde existe este freno ────────
        # Este bloque no existe en el backend local porque allí no hay costo real.
        if total_cost >= budget_usd:
            stop_reason = "budget"
            break
        # ─────────────────────────────────────────────────────────────────────

        response, in_tok, out_tok, cost = _call_claude(messages)
        total_in_tok  += in_tok
        total_out_tok += out_tok
        total_cost    += cost

        last_code = extract_code(response)
        success, error = run_tests(last_code)

        if success:
            stop_reason = "success"
            write_heartbeat({
                "backend": "claude", "run_id": run_id, "iteration": iteration,
                "status": "success", "cost_usd_so_far": round(total_cost, 6),
                "ts": datetime.now(timezone.utc).isoformat(),
            })
            return {
                "backend": "claude", "model": CLAUDE_MODEL, "run_id": run_id,
                "success": True, "iterations": iteration, "stop_reason": stop_reason,
                "wall_time_s": round(time.time() - start, 2),
                "input_tokens": total_in_tok, "output_tokens": total_out_tok,
                "cost_usd": round(total_cost, 6),
                "ts": datetime.now(timezone.utc).isoformat(),
            }

        # circuit breaker
        if error == last_error:
            consecutive += 1
        else:
            consecutive = 1
            last_error  = error

        if consecutive >= CIRCUIT_BREAKER_THRESHOLD:
            stop_reason = "circuit_breaker"
            break

        if iteration == max_iters:
            stop_reason = "step_cap"
            break

        messages.append({"role": "assistant", "content": response})
        messages.append({"role": "user", "content": build_correction_prompt(last_code, error)})

    write_heartbeat({
        "backend": "claude", "run_id": run_id, "iteration": iteration,
        "status": stop_reason, "cost_usd_so_far": round(total_cost, 6),
        "ts": datetime.now(timezone.utc).isoformat(),
    })
    return {
        "backend": "claude", "model": CLAUDE_MODEL, "run_id": run_id,
        "success": False, "iterations": iteration, "stop_reason": stop_reason,
        "wall_time_s": round(time.time() - start, 2),
        "input_tokens": total_in_tok, "output_tokens": total_out_tok,
        "cost_usd": round(total_cost, 6),
        "ts": datetime.now(timezone.utc).isoformat(),
    }

# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Loop engineering harness — brackets balanceados")
    parser.add_argument("--backend", choices=["local", "claude"], required=True)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--max-iters", type=int, default=DEFAULT_MAX_ITERS)
    parser.add_argument("--budget-usd", type=float, default=DEFAULT_BUDGET_USD,
                        help="Techo de presupuesto USD (SOLO aplica al backend claude)")
    args = parser.parse_args()

    RESULTS_DIR.mkdir(exist_ok=True)
    out_file = RESULTS_DIR / f"{args.backend}_runs.json"

    existing   = json.loads(out_file.read_text()) if out_file.exists() else []
    run_offset = len(existing)
    new_results = []

    for i in range(args.runs):
        run_id = run_offset + i + 1
        print(f"[{args.backend}] run {run_id} ...", end=" ", flush=True)

        if args.backend == "local":
            result = run_loop_local(args.max_iters, run_id)
        else:
            result = run_loop_claude(args.max_iters, args.budget_usd, run_id)

        status = "OK" if result["success"] else f"FAIL ({result['stop_reason']})"
        extra  = f", ${result['cost_usd']:.5f}" if args.backend == "claude" else ""
        print(f"{status} — {result['iterations']} iter, {result['wall_time_s']}s{extra}")

        new_results.append(result)

    all_results = existing + new_results
    out_file.write_text(json.dumps(all_results, indent=2))
    print(f"\nResultados guardados en: {out_file}")


if __name__ == "__main__":
    main()
