#!/usr/bin/env python3
"""Genera comparacion.png a partir de claude_runs.json y local_runs.json."""

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt

RESULTS_DIR = Path(__file__).parent / "results"


def load(path: Path) -> list[dict]:
    if not path.exists():
        print(f"Advertencia: {path} no existe", file=sys.stderr)
        return []
    return json.loads(path.read_text())


def stats(runs: list[dict]) -> dict:
    if not runs:
        return {}
    successes  = [r for r in runs if r["success"]]
    success_rate = len(successes) / len(runs) * 100
    avg_iters  = sum(r["iterations"] for r in runs) / len(runs)
    avg_time   = sum(r["wall_time_s"] for r in runs) / len(runs)
    avg_iters_success = (
        sum(r["iterations"] for r in successes) / len(successes) if successes else 0
    )
    return {
        "n": len(runs),
        "success_rate": success_rate,
        "avg_iters": avg_iters,
        "avg_iters_success": avg_iters_success,
        "avg_time": avg_time,
    }


def main() -> None:
    claude_runs = load(RESULTS_DIR / "claude_runs.json")
    local_runs  = load(RESULTS_DIR / "local_runs.json")

    if not claude_runs and not local_runs:
        print("Error: no hay resultados. Corre primero run_comparison.sh", file=sys.stderr)
        sys.exit(1)

    cs = stats(claude_runs) if claude_runs else {}
    ls = stats(local_runs) if local_runs else {}

    # Solo incluir backends con datos reales
    entries = []
    if cs:
        entries.append(("Claude\nHaiku 4.5", "#5B8CDB", cs))
    if ls:
        entries.append(("Qwen3 35B\n(local)", "#E07B39", ls))

    labels = [e[0] for e in entries]
    colors = [e[1] for e in entries]
    data   = [e[2] for e in entries]

    n_claude = cs.get("n", 0)
    n_local  = ls.get("n", 0)

    fig, axes = plt.subplots(1, 3, figsize=(12, 5))
    fig.suptitle(
        "Loop Engineering — Experimento 01: Brackets Balanceados\n"
        f"(Claude n={n_claude}, Qwen3 n={n_local})",
        fontsize=13, fontweight="bold", y=1.02,
    )

    def bar(ax, key, title, ylabel, fmt=".1f", suffix="", ylim_top=None):
        values = [d.get(key) for d in data]
        valid  = [v for v in values if v is not None]
        if not valid:
            ax.set_visible(False)
            return
        bars = ax.bar(labels, values, color=colors, width=0.45, edgecolor="white", linewidth=1.2)
        ax.set_title(title, fontsize=11, pad=10)
        ax.set_ylabel(ylabel, fontsize=9)
        top = ylim_top if ylim_top else max(valid) * 1.35
        ax.set_ylim(0, top or 1)
        ax.spines[["top", "right"]].set_visible(False)
        for b, v in zip(bars, values):
            if v is not None:
                ax.text(b.get_x() + b.get_width() / 2,
                        b.get_height() + 0.02 * ax.get_ylim()[1],
                        f"{v:{fmt}}{suffix}",
                        ha="center", va="bottom", fontsize=10, fontweight="bold")

    bar(axes[0], "success_rate", "Tasa de éxito", "%", fmt=".0f", suffix="%", ylim_top=120)
    bar(axes[1], "avg_iters", "Iteraciones promedio\n(todas las ejecuciones)", "iteraciones")
    bar(axes[2], "avg_time", "Tiempo promedio\n(segundos)", "s")

    fig.tight_layout()
    out = RESULTS_DIR / "comparacion.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"Gráfico guardado en: {out}")


if __name__ == "__main__":
    main()
