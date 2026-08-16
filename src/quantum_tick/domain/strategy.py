"""Master signal engine: the same 8-filter pipeline as dt_bot_v8.evaluate_signal,
but returning a structured result instead of mixing in logging. Pure function
of (candles, symbol, params, tracker) -> EvaluationResult; callers (live
service, backtester) decide what to do with skip reasons.
"""

from __future__ import annotations

from dataclasses import dataclass

from quantum_tick.domain.entries import detect_entry
from quantum_tick.domain.filters import (
    detect_bos_choch,
    detect_trend,
    has_large_fvg,
    has_post_impulse,
    is_choppy_market,
    is_late_entry,
)
from quantum_tick.domain.candles import avg_body_size, open_time
from quantum_tick.domain.models import Signal, StrategyParams
from quantum_tick.domain.state import FiredCandleTracker
from quantum_tick.domain.targets import estimate_duration, find_nearest_swing


@dataclass
class EvaluationResult:
    signal: Signal | None
    skip_reason: str | None = None
    detail: str = ""


def evaluate_signal(
    candles: list[dict],
    symbol: str,
    params: StrategyParams,
    tracker: FiredCandleTracker,
    *,
    check_late_entry: bool = True,
) -> EvaluationResult:
    """`check_late_entry=False` is used by the backtester, which has no
    sub-candle tick data to evaluate "has the forming candle already moved
    too far" against -- see backtesting/engine.py for the full rationale."""

    if len(candles) < params.min_candles_needed():
        return EvaluationResult(None, "insufficient_data")

    price = candles[-2]["close"]

    trend, reason = detect_trend(candles, params)
    if not trend:
        return EvaluationResult(None, "exhaustion" if reason == "exhaustion" else "trend")

    structure = detect_bos_choch(candles, trend, params)
    if not structure:
        return EvaluationResult(None, "structure")

    is_chop, chop_reason = is_choppy_market(candles, trend, params)
    if is_chop:
        return EvaluationResult(None, "choppy", chop_reason)

    if has_large_fvg(candles, trend, params):
        return EvaluationResult(None, "fvg")

    is_impulse, impulse_reason = has_post_impulse(candles, params)
    if is_impulse:
        return EvaluationResult(None, "post_impulse", impulse_reason)

    entries = detect_entry(candles, trend, params)
    if not entries:
        return EvaluationResult(None, "no_entry")

    if check_late_entry:
        is_late, late_reason = is_late_entry(candles, trend, params)
        if is_late:
            return EvaluationResult(None, "late_entry", late_reason)

    if tracker.is_same_candle(symbol, candles):
        return EvaluationResult(None, "same_candle")

    target, distance = find_nearest_swing(candles, trend, params)
    duration = estimate_duration(candles, distance, params)
    avg = avg_body_size(candles, params.avg_body_lookback)

    signal = Signal(
        symbol=symbol,
        contract_type="CALL" if trend == "BULLISH" else "PUT",
        trend=trend,
        structure=structure,
        entries=entries,
        target=target,
        distance=distance,
        avg_body=avg,
        duration_mins=duration,
        price=price,
        signal_open_time=open_time(candles[-2]),
    )
    return EvaluationResult(signal)
