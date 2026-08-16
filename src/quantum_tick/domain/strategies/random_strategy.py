"""Pure coin-flip baseline: no market logic at all, contract direction is a
fair 50/50 draw. This is the statistical control every real strategy should
be compared against -- if v8 or breakout can't beat this by a significant,
out-of-sample margin, they aren't adding anything a fair coin wouldn't.

Seeded by default for reproducibility: re-running the backtest reproduces
the same "random" trades rather than a different sample each time, so a
result can be checked/reported rather than only observed once.
"""

from __future__ import annotations

import random

from quantum_tick.domain.strategies.base import DetectedSignal


class RandomStrategy:
    name = "random"

    def __init__(self, duration_mins: int = 3, fire_probability: float = 1.0, seed: int = 42):
        self.duration_mins = duration_mins
        self.fire_probability = fire_probability
        self.required_window = 2  # only needs a "signal" and "forming" candle to exist
        self._rng = random.Random(seed)

    def detect(self, candles: list[dict], symbol: str) -> DetectedSignal | None:
        if self._rng.random() > self.fire_probability:
            return None
        contract_type = "CALL" if self._rng.random() < 0.5 else "PUT"
        return DetectedSignal(contract_type=contract_type, duration_mins=self.duration_mins, technique="random")
