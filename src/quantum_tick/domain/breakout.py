"""Donchian channel breakout -- a genuinely different strategy family from
the v8 trend/BOS-CHoCH/entry-pattern ruleset (not a parameter variant of
it). Classic, well-known rule, not fit to this project's data: price
closing outside the highest-high/lowest-low of the last N closed candles
signals a breakout in that direction.

Parameters (channel_lookback=20, a canonical Donchian/Turtle-Trading
default; duration_mins=3) are fixed *before* looking at backtest results
and are not tuned afterward -- swept until something clears p<0.05 is
exactly the overfitting trap docs/postmortem/PROJECT_POSTMORTEM.md item 19
and docs/research/RESEARCH_FINDINGS.md warn about.
"""

from __future__ import annotations


def detect_breakout(candles: list[dict], channel_lookback: int) -> str | None:
    """`candles[-2]` is the signal candle (just closed); the channel is the
    `channel_lookback` closed candles before it. Returns "CALL"/"PUT"/None."""

    window = candles[-(channel_lookback + 2) : -2]
    if len(window) < channel_lookback:
        return None

    signal = candles[-2]
    highest = max(c["high"] for c in window)
    lowest = min(c["low"] for c in window)

    if signal["close"] > highest:
        return "CALL"
    if signal["close"] < lowest:
        return "PUT"
    return None
