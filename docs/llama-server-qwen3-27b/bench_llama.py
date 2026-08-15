#!/usr/bin/env python3
"""
bench_llama.py — medición de rendimiento de llama-server (Qwen3.8-27B, RTX 3090)

Valida la configuración de docs/llama-server-qwen3-27b/ midiendo contra un
endpoint OpenAI-compatible:

  - time-to-first-token (TTFT), en segundos
  - velocidad de generación (tokens/s), sobre tokens de contenido
  - latencia total por petición (segundos)
  - (opcional, --vram) uso de VRAM pico vía nvidia-smi durante la corrida

Puede apuntar al llama-server directo (:8080) o al proxy LiteLLM (:4000):

  # contra llama-server directo (valida la config de llama-server)
  python3 bench_llama.py

  # a través de LiteLLM (valida la integración del lab)
  python3 bench_llama.py \
      --base-url http://localhost:4000/v1 \
      --api-key sk-litellm-local \
      --model qwen3

  # corrida más larga, con muestreo de VRAM
  python3 bench_llama.py --runs 5 --max-tokens 512 --vram

Requisitos: `pip install -r requirements.txt` (usa la librería `openai`).
Para --vram hace falta `nvidia-smi` en el PATH.
"""

import argparse
import json
import statistics
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

# ── configuración ────────────────────────────────────────────────────────────

DEFAULT_BASE_URL = "http://127.0.0.1:8080/v1"
DEFAULT_API_KEY  = "sk-llamacpp"          # llama-server no la valida; LiteLLM sí
DEFAULT_MODEL    = "qwen3.8-27b"          # informativo para llama-server directo
DEFAULT_PROMPT   = (
    "Escribe una función Python que invierta una lista sin usar [::-1] "
    "y explica en una frase por qué funciona."
)

RESULTS_DIR = Path(__file__).parent / "results"


# ── VRAM (nvidia-smi) ────────────────────────────────────────────────────────

def sample_vram() -> dict | None:
    """Lee memoria usada/total y utilización de la GPU 0. None si no hay nvidia-smi."""
    try:
        out = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.used,memory.total,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode != 0 or not out.stdout.strip():
            return None
        used, total, util = (p.strip() for p in out.stdout.strip().splitlines()[0].split(","))
        return {
            "used_mib": int(used),
            "total_mib": int(total),
            "util_pct": int(util),
        }
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, IndexError):
        return None


class VramSampler(threading.Thread):
    """Muestrea nvidia-smi en segundo plano y guarda el pico de memoria usada."""

    def __init__(self, interval: float = 0.5) -> None:
        super().__init__(daemon=True)
        self.interval = interval
        self._stop = threading.Event()
        self._samples: list[dict] = []
        self._lock = threading.Lock()

    def run(self) -> None:
        while not self._stop.is_set():
            sample = sample_vram()
            if sample is not None:
                with self._lock:
                    self._samples.append(sample)
            self._stop.wait(self.interval)

    def stop_and_peak(self) -> dict | None:
        self._stop.set()
        self.join(timeout=2)
        with self._lock:
            if not self._samples:
                return None
            return max(self._samples, key=lambda s: s["used_mib"])


# ── medición de una petición ─────────────────────────────────────────────────

def run_once(client, model: str, prompt: str, max_tokens: int) -> dict:
    """Hace una petición con streaming y mide TTFT, tokens y tiempos."""
    t_start  = time.time()
    t_first  = None
    t_last   = None
    ttft     = None
    first_kind = None
    usage    = None
    content_chunks = 0

    stream = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        stream=True,
        stream_options={"include_usage": True},
    )

    for chunk in stream:
        if not chunk.choices:
            # chunk final de uso (solo con stream_options={"include_usage": True})
            if getattr(chunk, "usage", None) is not None:
                usage = chunk.usage
            continue

        delta     = chunk.choices[0].delta
        text      = getattr(delta, "content", None) or ""
        reasoning = getattr(delta, "reasoning_content", None) or ""

        if ttft is None and (text or reasoning):
            ttft       = time.time() - t_start
            t_first    = time.time()
            first_kind = "reasoning" if (reasoning and not text) else "content"

        if text or reasoning:
            t_last = time.time()

        if text:
            content_chunks += 1

    total_s = time.time() - t_start
    completion_tokens = getattr(usage, "completion_tokens", None) if usage else None
    prompt_tokens     = getattr(usage, "prompt_tokens", None) if usage else None

    # Si el endpoint no reporta usage en streaming, estima con los chunks de texto.
    if completion_tokens is None:
        completion_tokens = content_chunks

    gen_s   = (t_last - t_first) if (t_last and t_first) else None
    gen_tps = (completion_tokens / gen_s) if (gen_s and gen_s > 0) else None
    total_tps = (completion_tokens / total_s) if total_s > 0 else None

    return {
        "ttft_s": round(ttft, 3) if ttft is not None else None,
        "first_token_kind": first_kind,
        "gen_time_s": round(gen_s, 3) if gen_s is not None else None,
        "gen_tokens_per_s": round(gen_tps, 2) if gen_tps is not None else None,
        "total_s": round(total_s, 3),
        "total_tokens_per_s": round(total_tps, 2) if total_tps is not None else None,
        "completion_tokens": completion_tokens,
        "prompt_tokens": prompt_tokens,
    }


# ── resumen ──────────────────────────────────────────────────────────────────

def summarize(runs: list[dict]) -> dict:
    def mean(key: str):
        values = [r[key] for r in runs if r.get(key) is not None]
        return round(statistics.mean(values), 2) if values else None

    def lo(key: str):
        values = [r[key] for r in runs if r.get(key) is not None]
        return round(min(values), 2) if values else None

    def hi(key: str):
        values = [r[key] for r in runs if r.get(key) is not None]
        return round(max(values), 2) if values else None

    return {
        "runs": len(runs),
        "ttft_s_avg": mean("ttft_s"),
        "ttft_s_min": lo("ttft_s"),
        "ttft_s_max": hi("ttft_s"),
        "gen_tokens_per_s_avg": mean("gen_tokens_per_s"),
        "total_tokens_per_s_avg": mean("total_tokens_per_s"),
        "total_s_avg": mean("total_s"),
    }


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark de llama-server: TTFT, tokens/s y (opcional) VRAM"
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--api-key", default=DEFAULT_API_KEY)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--max-tokens", type=int, default=256)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--vram", action="store_true",
                        help="muestrea nvidia-smi durante la corrida y reporta el pico")
    args = parser.parse_args()

    # import diferido para no exigir openai si solo se pide --help
    from openai import OpenAI
    client = OpenAI(base_url=args.base_url, api_key=args.api_key)

    sampler = VramSampler() if args.vram else None
    if sampler is not None:
        sampler.start()

    runs: list[dict] = []
    print(f"Benchmark contra {args.base_url} (modelo '{args.model}')")
    print(f"{args.runs} peticiones × max_tokens={args.max_tokens}\n")

    try:
        for i in range(1, args.runs + 1):
            print(f"[run {i}/{args.runs}]", end=" ", flush=True)
            try:
                result = run_once(client, args.model, args.prompt, args.max_tokens)
                runs.append(result)
                if result["ttft_s"] is not None:
                    print(
                        f"TTFT {result['ttft_s']}s · "
                        f"{result['gen_tokens_per_s']} tok/s gen · "
                        f"{result['completion_tokens']} tokens"
                    )
                else:
                    print("sin tokens (revisa el endpoint)")
            except Exception as exc:  # noqa: BLE001 — el bench debe seguir con las demás runs
                print(f"ERROR: {exc}")
    finally:
        if sampler is not None:
            peak = sampler.stop_and_peak()
        else:
            peak = None

    if not runs:
        print("\nNo se completó ninguna petición. Verifica que el servidor esté arriba.")
        sys.exit(1)

    summary = summarize(runs)
    print("\n── Resumen ──")
    print(f"  TTFT            : avg {summary['ttft_s_avg']}s "
          f"(min {summary['ttft_s_min']}s / max {summary['ttft_s_max']}s)")
    print(f"  Velocidad gen.  : avg {summary['gen_tokens_per_s_avg']} tok/s")
    print(f"  Velocidad total : avg {summary['total_tokens_per_s_avg']} tok/s (incluye TTFT)")
    print(f"  Latencia total  : avg {summary['total_s_avg']}s por petición")

    if peak is not None:
        print("\n── VRAM (nvidia-smi, pico de la corrida) ──")
        print(f"  Memoria usada   : {peak['used_mib']} MiB / {peak['total_mib']} MiB")
        print(f"  Utilización GPU : {peak['util_pct']}%")

    RESULTS_DIR.mkdir(exist_ok=True)
    out_file = RESULTS_DIR / "bench.json"
    existing = json.loads(out_file.read_text()) if out_file.exists() else []
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "base_url": args.base_url,
        "model": args.model,
        "max_tokens": args.max_tokens,
        "runs": runs,
        "summary": summary,
        "vram_peak": peak,
    }
    existing.append(record)
    out_file.write_text(json.dumps(existing, indent=2, ensure_ascii=False))
    print(f"\nResultados guardados en: {out_file}")


if __name__ == "__main__":
    main()
