[🇬🇧 English](README.md) · [🇪🇸 Castellano](README.es.md)

---

# loop-engineering-lab

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)

> **TL;DR** — Loop engineering means designing the *system around the agent*, not just the prompt.
> This repo is a growing lab of experiments: each one runs a real agent loop, measures it with
> deterministic tests, and shows what happens when you add proper brakes (step cap, circuit breaker,
> heartbeat, budget ceiling). Experiment 01 compares Claude Haiku vs. Qwen3-35B local on a
> bracket-balancing task where naive solutions reliably fail.

## What is loop engineering

Loop engineering means designing the system that surrounds an agent, not just the prompt you give it.
It has two inseparable halves: the **engine** (making the agent act on something real, observe the
real result, and decide on its own when to stop) and the **brakes** (explicitly limiting how much
damage it can do while no one is watching).

An agent without an engine is a chatbot. An agent without brakes is a system that can iterate
indefinitely, spend unlimited money, or break things silently. Loop engineering means having both
halves at once, with the 6 required pieces: persistent state, automation, isolation (blast radius),
skills, connectors, and maker/checker sub-agents.

→ Full explanation in [`docs/loop-engineering-explicado.md`](docs/loop-engineering-explicado.md)

---

## Experiments

| # | Task | Models | Status |
|---|------|--------|--------|
| [01 — Brackets](experiments/01-brackets/) | `is_balanced(s)`: detect balanced brackets | Qwen3-35B local vs. Claude Haiku 4.5 | ✓ Complete |

*More experiments coming: more complex tasks, external tools via MCP, multi-agent loops.*

---

## Real results (n=5 runs per backend)

| Metric | Claude Haiku 4.5 | Qwen3-35B (local) |
|--------|-----------------|-------------------|
| Success rate | 100% (5/5) | 100% (5/5) |
| Avg iterations | 1.0 | 1.8 |
| Iteration range | 1–1 | 1–3 |
| Avg wall time | 1.3 s | 72.5 s |
| Avg cost | $0.00078 | $0 (local) |
| Total cost (5 runs) | $0.0039 | — |

Claude Haiku solves the task correctly on the first iteration every time.
Qwen3-35B local needs 1–3 attempts (avg 1.8) because its reasoning mode sometimes reaches a
counting-based solution before self-correcting to a stack. Both models achieve 100% success.
The time difference (1.3s vs 72.5s) reflects Qwen3's thinking overhead plus network latency to
Anthropic versus local inference.

![Comparison](experiments/01-brackets/results/comparacion.png)

---

## Structure

```
loop-engineering-lab/
├── docs/
│   └── loop-engineering-explicado.md   # full theory with code examples
└── experiments/
    └── 01-brackets/
        ├── loop.py                     # harness with both backends and 4 brakes
        ├── plot.py                     # generates comparacion.png
        ├── run_comparison.sh           # runs N executions and generates the chart
        ├── skills/balanced_brackets/
        │   └── SKILL.md               # task specification (outside the code)
        └── results/
            ├── local_runs.json
            ├── claude_runs.json        # generated when running with ANTHROPIC_API_KEY
            └── comparacion.png
```

---

## How to run

```bash
pip install -r requirements.txt

# Local backend only (Qwen3 via LiteLLM at localhost:4000)
cd experiments/01-brackets
python3 loop.py --backend local --runs 5

# Both backends
export ANTHROPIC_API_KEY=sk-...
bash run_comparison.sh 5
```

---

## Harness design

The budget brake exists **literally only** in the Claude backend code path — there is no `budget`
variable in the local backend code, because there is no real cost there. This separation is
intentional: a brake that does not apply should not exist in the code path where it does not apply.

The "checker" is the Python interpreter running deterministic tests, not the model evaluating
itself. The maker/checker separation is what makes the loop converge instead of the model always
saying yes.
