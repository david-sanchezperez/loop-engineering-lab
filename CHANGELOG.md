# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Fixed

- `experiments/01-brackets/plot.py`: eliminado el import muerto de `numpy` y
  `matplotlib.patches` (no se usaban) y corregido el docstring, que
  mencionaba un `qwen_runs.json` inexistente — el script lee `local_runs.json`.
