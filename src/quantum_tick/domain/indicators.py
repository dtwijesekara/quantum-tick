"""SMA / EMA / RSI / MACD -- the indicator vocabulary actually used across
the ORSTAC XML bot corpus (see docs/research/RESEARCH_FINDINGS.md section
8); no Bollinger/Stochastic/ADX block types exist there.

Each function takes a plain `list[float]` price series (oldest-first) so
the same implementation works for candle closes or raw ticks.
"""

from __future__ import annotations


def sma(series: list[float], period: int) -> float | None:
    if len(series) < period:
        return None
    window = series[-period:]
    return sum(window) / period


def ema_series(series: list[float], period: int) -> list[float]:
    """Full EMA series (not just the latest value) -- MACD needs the whole
    series to compute a signal-line EMA of the MACD line itself."""
    if len(series) < period:
        return []
    k = 2 / (period + 1)
    seed = sum(series[:period]) / period
    out = [seed]
    for price in series[period:]:
        out.append(price * k + out[-1] * (1 - k))
    return out


def ema(series: list[float], period: int) -> float | None:
    values = ema_series(series, period)
    return values[-1] if values else None


def rsi(series: list[float], period: int) -> float | None:
    """Wilder's RSI. Needs `period + 1` prices (period deltas)."""
    if len(series) < period + 1:
        return None

    window = series[-(period + 1):]
    deltas = [b - a for a, b in zip(window, window[1:])]
    gains = [d if d > 0 else 0.0 for d in deltas]
    losses = [-d if d < 0 else 0.0 for d in deltas]

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def macd(series: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[float, float, float] | None:
    """Returns (macd_line, signal_line, histogram), or None if there isn't
    enough history yet."""
    fast_values = ema_series(series, fast)
    slow_values = ema_series(series, slow)
    if not fast_values or not slow_values:
        return None

    # align both EMA series to the same trailing window before subtracting
    n = min(len(fast_values), len(slow_values))
    macd_line_series = [f - s for f, s in zip(fast_values[-n:], slow_values[-n:])]

    signal_values = ema_series(macd_line_series, signal)
    if not signal_values:
        return None

    macd_line = macd_line_series[-1]
    signal_line = signal_values[-1]
    return macd_line, signal_line, macd_line - signal_line
