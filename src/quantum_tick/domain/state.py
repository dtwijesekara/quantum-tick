"""Per-symbol "already fired on this candle" lock.

Explicit, instantiable object rather than a module-level global dict --
dt_bot_v8.py used a single global `last_signal_open`, which is fine for one
live process but would leak state across symbols/runs if reused inside a
backtester that evaluates many symbols and many historical windows in the
same process.
"""

from __future__ import annotations

from quantum_tick.domain.candles import open_time


class FiredCandleTracker:
    def __init__(self) -> None:
        self._last_signal_open: dict[str, int] = {}

    def is_same_candle(self, symbol: str, candles: list[dict]) -> bool:
        signal_candle_open = open_time(candles[-2])
        return self._last_signal_open.get(symbol) == signal_candle_open

    def mark_fired(self, symbol: str, candles: list[dict]) -> None:
        self._last_signal_open[symbol] = open_time(candles[-2])
