"""Entry techniques: ENGULFING and HOP. See dt_bot_v8.py docstring for the
rationale (ONE_COLOR was removed as an entry signal in v8 -- it's now only
a trend filter)."""

from __future__ import annotations

from quantum_tick.domain.candles import avg_body_size, body, color
from quantum_tick.domain.models import StrategyParams


def detect_entry(candles: list[dict], trend: str, params: StrategyParams) -> list[str]:
    entries: list[str] = []
    curr = candles[-2]
    prev = candles[-3]
    avg = avg_body_size(candles, params.avg_body_lookback)

    curr_color = color(curr)
    prev_color = color(prev)
    curr_body = body(curr)
    prev_body = body(prev)

    if prev_body > 0:
        if trend == "BULLISH" and prev_color == "RED" and curr_color == "GREEN":
            cov = (curr["close"] - min(prev["open"], prev["close"])) / prev_body
            if cov >= params.engulf_coverage and curr_body >= prev_body * 0.7:
                entries.append("ENGULFING")
        elif trend == "BEARISH" and prev_color == "GREEN" and curr_color == "RED":
            cov = (max(prev["open"], prev["close"]) - curr["close"]) / prev_body
            if cov >= params.engulf_coverage and curr_body >= prev_body * 0.7:
                entries.append("ENGULFING")

    min_gap = avg * params.hop_min_body_mult
    if trend == "BULLISH":
        gap = prev["close"] - curr["open"]
        if gap >= min_gap and curr_color == "GREEN":
            entries.append("HOP")
    elif trend == "BEARISH":
        gap = curr["open"] - prev["close"]
        if gap >= min_gap and curr_color == "RED":
            entries.append("HOP")

    return entries
