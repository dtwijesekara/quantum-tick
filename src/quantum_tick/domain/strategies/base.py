"""Shared interface every strategy (v8, breakout, random, xmlbot, or a
future one) implements, so backtesting/engine.py needs exactly one replay
loop instead of one per strategy -- adding a strategy means adding a class
here, nothing else in the backtester changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class DetectedSignal:
    contract_type: str  # "CALL" or "PUT"
    duration_mins: int
    technique: str = ""


class Strategy(Protocol):
    name: str
    required_window: int  # how many trailing candles `detect` needs to see

    def detect(self, candles: list[dict], symbol: str) -> DetectedSignal | None:
        """`candles` is oldest-first; `candles[-1]` is the "forming" candle
        (the entry candle if a signal fires) and `candles[-2]` is the last
        fully-closed candle. Must not mutate `candles`. May hold internal
        state (e.g. a same-candle lock) between calls, but a fresh Strategy
        instance is used per backtest run/symbol so state never leaks
        across runs."""
        ...
