"""Aim level (nearest swing) and duration estimate. See dt_bot_v8.py."""

from __future__ import annotations

from quantum_tick.domain.candles import avg_body_size
from quantum_tick.domain.models import StrategyParams


def find_nearest_swing(candles: list[dict], trend: str, params: StrategyParams) -> tuple[float, float]:
    s = params.swing_strength
    closed = candles[-(params.swing_lookback + s + 2):-1]
    price = candles[-2]["close"]

    nearest_price: float | None = None
    nearest_distance = float("inf")

    for i in range(s, len(closed) - s):
        c = closed[i]
        if trend == "BULLISH":
            ok = all(c["high"] >= closed[i - j]["high"] for j in range(1, s + 1)) and all(
                c["high"] >= closed[i + j]["high"] for j in range(1, s + 1)
            )
            if ok and c["high"] > price:
                d = c["high"] - price
                if d < nearest_distance:
                    nearest_distance = d
                    nearest_price = c["high"]
        else:
            ok = all(c["low"] <= closed[i - j]["low"] for j in range(1, s + 1)) and all(
                c["low"] <= closed[i + j]["low"] for j in range(1, s + 1)
            )
            if ok and c["low"] < price:
                d = price - c["low"]
                if d < nearest_distance:
                    nearest_distance = d
                    nearest_price = c["low"]

    if nearest_price is None:
        recent = candles[-params.swing_lookback:-1]
        if trend == "BULLISH":
            nearest_price = max(c["high"] for c in recent)
        else:
            nearest_price = min(c["low"] for c in recent)
        nearest_distance = abs(nearest_price - price)

    return nearest_price, nearest_distance


def estimate_duration(candles: list[dict], distance: float, params: StrategyParams) -> int:
    avg = avg_body_size(candles, params.avg_body_lookback)
    raw = distance / avg if avg > 0 else params.min_duration_mins
    return int(max(params.min_duration_mins, min(params.max_duration_mins, round(raw + 0.5))))
