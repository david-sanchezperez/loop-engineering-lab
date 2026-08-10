"""brakes.py — frenos compartidos para los loops de agente (NOOA y clásico).

Encapsula los 4 frenos del experimento 01 en una sola clase para que ambos
enfoques del experimento 02 (NOOA y tool-calling clásico) los reusen
idénticamente:

  1. Step cap        → ``max_iters`` (default 10)
  2. Circuit breaker → mismo error 3 veces seguidas → para
  3. Heartbeat       → ``loop_state.json`` actualizado en cada iteración
  4. Budget ceiling  → SOLO backend claude (no existe en local/mock)

Mantener estos frenos en un solo módulo garantiza que la comparación NOOA
vs. clásico aisle la arquitectura del agente y no el control de seguridad:
ambos enfoques corren bajo exactamente las mismas salvaguardas.
"""

import json
from pathlib import Path

CIRCUIT_BREAKER_THRESHOLD = 3
DEFAULT_MAX_ITERS = 10
DEFAULT_BUDGET_USD = 0.10   # solo se usa en backend claude


class Brakes:
    """Frenos de seguridad compartidos por los loops NOOA y clásico.

    El ``backend`` determina qué frenos aplican: el techo de presupuesto
    SOLO existe para ``backend == "claude"`` (igual que en el experimento 01,
    donde no aparece en el código del backend local). El step cap, el circuit
    breaker y el heartbeat aplican a todos los backends.
    """

    def __init__(
        self,
        max_iters: int = DEFAULT_MAX_ITERS,
        budget_usd: float = DEFAULT_BUDGET_USD,
        backend: str | None = None,
        state_file: Path | None = None,
    ) -> None:
        self.max_iters = max_iters
        self.budget_usd = budget_usd
        self.backend = backend
        self.state_file = state_file
        self.last_error: str | None = None
        self.consecutive_errors = 0
        self.total_cost = 0.0

    @property
    def budget_enforced(self) -> bool:
        """El techo de presupuesto SOLO aplica al backend claude."""
        return self.backend == "claude"

    def budget_exceeded(self, cost_so_far: float) -> bool:
        """True si el costo acumulado supera el techo (solo backend claude)."""
        if not self.budget_enforced:
            return False
        return cost_so_far >= self.budget_usd

    def register_error(self, error: str) -> bool:
        """Registra un error del modelo y actualiza el circuit breaker.

        Retorna ``True`` si el circuit breaker se disparó
        (``CIRCUIT_BREAKER_THRESHOLD`` errores idénticos seguidos).
        """
        if error == self.last_error:
            self.consecutive_errors += 1
        else:
            self.consecutive_errors = 1
            self.last_error = error
        return self.consecutive_errors >= CIRCUIT_BREAKER_THRESHOLD

    def circuit_tripped(self) -> bool:
        """True si el circuit breaker está disparado en este momento."""
        return self.consecutive_errors >= CIRCUIT_BREAKER_THRESHOLD

    def heartbeat(self, state: dict) -> None:
        """Escribe el estado del loop en ``loop_state.json`` (si hay state_file)."""
        if self.state_file is None:
            return
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(state, indent=2))
