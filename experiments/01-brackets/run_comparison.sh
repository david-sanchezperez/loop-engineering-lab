#!/usr/bin/env bash
# run_comparison.sh — corre N corridas de cada backend y genera comparacion.png

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

RUNS="${1:-5}"
MAX_ITERS="${2:-10}"

echo "========================================="
echo " Loop Engineering — Experimento 01"
echo " Tarea: is_balanced (brackets balanceados)"
echo " Corridas por backend: $RUNS"
echo " Máx iteraciones por corrida: $MAX_ITERS"
echo "========================================="
echo

# ── backend local (Qwen3 via LiteLLM) ────────────────────────────────────────
echo ">>> Backend LOCAL (Qwen3 35B cuantizado)"
python loop.py --backend local --runs "$RUNS" --max-iters "$MAX_ITERS"
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
