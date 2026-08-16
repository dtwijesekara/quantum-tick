from __future__ import annotations

from quantum_tick.domain.breakout import detect_breakout
from quantum_tick.domain.strategies.base import DetectedSignal


class BreakoutStrategy:
    """Adapter over domain/breakout.py's Donchian channel breakout."""

    name = "breakout"

    def __init__(self, channel_lookback: int = 20, duration_mins: int = 3):
        self.channel_lookback = channel_lookback
        self.duration_mins = duration_mins
        self.required_window = channel_lookback + 2

    def detect(self, candles: list[dict], symbol: str) -> DetectedSignal | None:
        contract_type = detect_breakout(candles, self.channel_lookback)
        if contract_type is None:
            return None
        return DetectedSignal(contract_type=contract_type, duration_mins=self.duration_mins, technique="breakout")
