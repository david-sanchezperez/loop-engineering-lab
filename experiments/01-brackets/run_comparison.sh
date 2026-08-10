#!/usr/bin/env bash
# run_comparison.sh — lanza N ejecuciones de cada backend y genera comparacion.png
#
# Uso: bash run_comparison.sh [RUNS] [MAX_ITERS]
#   RUNS      → ejecuciones por backend (default: 5)
#   MAX_ITERS → máx iteraciones por ejecución (default: 10)
#
# Backends:
#   local   → Qwen3 35B via LiteLLM / llama.cpp  (localhost:4000)
#   muse    → Muse-Glimmer-30B-GGUF via llama.cpp  (localhost:8080)
#   claude  → Claude Haiku 4.5  (requiere ANTHROPIC_API_KEY)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

RUNS="${1:-5}"
MAX_ITERS="${2:-10}"

echo "========================================="
echo " Loop Engineering — Experimento 01"
echo " Tarea: is_balanced (brackets balanceados)"
echo " Ejecuciones por backend: $RUNS"
echo " Máx iteraciones por ejecución: $MAX_ITERS"
echo "========================================="
echo

# ── backend local (Qwen3 via LiteLLM) ────────────────────────────────────────
echo ">>> Backend LOCAL (Qwen3 35B cuantizado)"
python loop.py --backend local --runs "$RUNS" --max-iters "$MAX_ITERS"
echo

# ── backend Muse-Glimmer-30B (llama.cpp server) ──────────────────────────────
echo ">>> Backend MUSE (Muse-Glimmer-30B-GGUF via llama.cpp)"
python loop.py --backend muse --runs "$RUNS" --max-iters "$MAX_ITERS"
echo

# ── backend Claude ────────────────────────────────────────────────────────────
if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
    echo ">>> Backend CLAUDE: ANTHROPIC_API_KEY no está definida — saltando"
    echo "    Para incluir Claude: export ANTHROPIC_API_KEY=sk-... && bash run_comparison.sh"
else
    echo ">>> Backend CLAUDE (claude-haiku-4-5)"
    python loop.py --backend claude --runs "$RUNS" --max-iters "$MAX_ITERS"
    echo
fi

# ── gráfico ────────────────────────────────────────────────────────────────────
echo ">>> Generando gráfico comparativo..."
python plot.py
echo
echo "Listo. Revisa results/comparacion.png"
