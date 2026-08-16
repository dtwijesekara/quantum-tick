from __future__ import annotations

from quantum_tick.domain.models import StrategyParams
from quantum_tick.domain.state import FiredCandleTracker
from quantum_tick.domain.strategy import evaluate_signal
from quantum_tick.domain.strategies.base import DetectedSignal


class V8Strategy:
    """Adapter over domain/strategy.py's evaluate_signal (trend + BOS/CHoCH +
    ENGULFING/HOP entries + 5 filters) -- see legacy/dt_bot_v8.py for the
    original, single-file version this was extracted from."""

    name = "v8"

    def __init__(self, params: StrategyParams | None = None):
        self.params = params or StrategyParams()
        self.required_window = self.params.min_candles_needed()
        self._tracker = FiredCandleTracker()

    def detect(self, candles: list[dict], symbol: str) -> DetectedSignal | None:
        result = evaluate_signal(candles, symbol, self.params, self._tracker, check_late_entry=False)
        if result.skip_reason:
            return None

        signal = result.signal
        self._tracker.mark_fired(symbol, candles)
        return DetectedSignal(
            contract_type=signal.contract_type,
            duration_mins=signal.duration_mins,
            technique="+".join(signal.entries),
        )
