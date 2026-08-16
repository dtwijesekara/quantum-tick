"""Shared interface every strategy (v8, breakout, random-baseline, or a
future one) implements, so backtesting/engine.py needs exactly one replay
loop instead of one per strategy. Previously v8 and breakout each had their
own near-identical engine (backtesting/engine.py vs breakout_engine.py) --
this is what "the same system can align to a new strategy" means concretely:
add a new class here, nothing else in the backtester changes.
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
        state (e.g. a same-candle lock) between calls for the same symbol,
        but a fresh Strategy instance is used per backtest run/symbol so
        state never leaks across runs -- see
        docs/postmortem/PROJECT_POSTMORTEM.md item 15's "inject, don't
        import a global" lesson, applied to strategy state instead of a DB
        session."""
        ...
