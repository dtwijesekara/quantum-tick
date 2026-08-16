"""Thin logging wrapper around domain.strategy.evaluate_signal, mirroring
dt_bot_v8's per-symbol diagnostic trail. Kept separate from the pure domain
logic so the strategy itself stays testable without a logger."""

from __future__ import annotations

import logging

from quantum_tick.domain.models import Signal, StrategyParams
from quantum_tick.domain.state import FiredCandleTracker
from quantum_tick.domain.strategy import evaluate_signal

log = logging.getLogger("quantum_tick.signal_service")

_SKIP_LABELS = {
    "insufficient_data": "insufficient_data",
    "exhaustion": "EXHAUSTED",
    "trend": "no_trend",
    "structure": "no BOS/CHoCH",
    "choppy": "choppy",
    "fvg": "large_fvg",
    "post_impulse": "post_impulse",
    "no_entry": "need ENGULFING or HOP",
    "late_entry": "late_entry",
    "same_candle": "already fired this candle",
}


class SignalService:
    def __init__(self, params: StrategyParams):
        self._params = params
        self._tracker = FiredCandleTracker()
        self.skip_counts: dict[str, int] = {}
        self.technique_counts: dict[str, int] = {"ENGULFING": 0, "HOP": 0}

    def evaluate(self, candles: list[dict], symbol: str) -> Signal | None:
        result = evaluate_signal(candles, symbol, self._params, self._tracker, check_late_entry=True)

        if result.skip_reason:
            self.skip_counts[result.skip_reason] = self.skip_counts.get(result.skip_reason, 0) + 1
            label = _SKIP_LABELS.get(result.skip_reason, result.skip_reason)
            detail = f" {result.detail}" if result.detail else ""
            log.info(f"  [{symbol}] SKIP {label}{detail}")
            return None

        signal = result.signal
        self._tracker.mark_fired(symbol, candles)
        for technique in signal.entries:
            self.technique_counts[technique] = self.technique_counts.get(technique, 0) + 1

        log.info(f"  [{symbol}] OK   trend={signal.trend} structure={signal.structure} entries={signal.entries}")
        log.info(f"  [{symbol}] OK   target={signal.target:.4f} dist={signal.distance:.4f} "
                  f"avg={signal.avg_body:.4f} => {signal.duration_mins}min")
        return signal
