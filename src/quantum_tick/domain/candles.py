"""Candle helpers shared by every strategy filter.

`open_time` falls back from `open_time` to `epoch` because the two Deriv
response shapes disagree: live `ohlc` pushes carry both (`epoch` = latest
tick time, `open_time` = stable candle-open id), while historical/snapshot
`candles` list entries only ever carry `epoch` (which *is* the open time
there). See docs/postmortem/PROJECT_POSTMORTEM.md item 7.
"""

from __future__ import annotations

Candle = dict  # {"open", "high", "low", "close", "epoch"/"open_time", ...}


def open_time(c: Candle) -> int:
    return c.get("open_time", c.get("epoch", 0))


def is_green(c: Candle) -> bool:
    return c["close"] > c["open"]


def color(c: Candle) -> str:
    return "GREEN" if is_green(c) else "RED"


def body(c: Candle) -> float:
    return abs(c["close"] - c["open"])


def avg_body_size(candles: list[Candle], lookback: int) -> float:
    window = candles[-(lookback + 1):-1]
    bodies = [body(c) for c in window if body(c) > 0]
    return (sum(bodies) / len(bodies)) if bodies else 0.0001
