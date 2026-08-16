"""The seven signal filters from dt_bot_v8, extracted as pure functions.

Each takes `candles` (oldest-first, last entry = currently forming) plus
`StrategyParams` and returns either a decision or `(bool, reason)`. No
logging, no global state -- callers (SignalEngine, backtester) decide what
to do with the result. Behavior is unchanged from dt_bot_v8.py; only the
hardcoded globals became explicit parameters.
"""

from __future__ import annotations

from quantum_tick.domain.candles import avg_body_size, body, color
from quantum_tick.domain.models import StrategyParams


def detect_trend(candles: list[dict], params: StrategyParams) -> tuple[str | None, str | None]:
    closed = candles[-(params.trend_max_candles + 4):-1]
    colors = [color(c) for c in closed]

    last_color = colors[-1]
    run = 0
    for c in reversed(colors):
        if c == last_color:
            run += 1
        else:
            break

    if run > params.trend_max_candles:
        return None, "exhaustion"

    if run >= params.trend_min_candles:
        trend = "BULLISH" if last_color == "GREEN" else "BEARISH"
        return trend, None

    return None, "no_trend"


def detect_bos_choch(candles: list[dict], trend: str, params: StrategyParams) -> str | None:
    window = candles[-(params.bos_lookback + 2):-2]
    current = candles[-2]
    if len(window) < 4:
        return None

    swing_high = max(c["high"] for c in window)
    swing_low = min(c["low"] for c in window)
    prior = [color(c) for c in window[: len(window) // 2]]

    if trend == "BULLISH" and current["close"] > swing_high:
        had_bear = prior.count("RED") > prior.count("GREEN")
        return "CHoCH" if had_bear else "BOS"

    if trend == "BEARISH" and current["close"] < swing_low:
        had_bull = prior.count("GREEN") > prior.count("RED")
        return "CHoCH" if had_bull else "BOS"

    return None


def is_choppy_market(candles: list[dict], trend: str, params: StrategyParams) -> tuple[bool, str]:
    window = candles[-(params.chop_lookback + 2):-1]
    if len(window) < params.chop_lookback:
        return False, ""

    signals_fired = []
    colors = [color(c) for c in window]

    alternations = sum(1 for i in range(len(colors) - 1) if colors[i] != colors[i + 1])
    alter_rate = alternations / (len(colors) - 1)
    if alter_rate > params.chop_alter_threshold:
        signals_fired.append(f"alternation={alter_rate:.0%}")

    recent_bodies = [body(c) for c in window[-4:] if body(c) > 0]
    baseline_bodies = [body(c) for c in window if body(c) > 0]
    if recent_bodies and baseline_bodies:
        ratio = (sum(recent_bodies) / len(recent_bodies)) / (sum(baseline_bodies) / len(baseline_bodies))
        if ratio < params.chop_body_threshold:
            signals_fired.append(f"body_shrink={ratio:.0%}")

    trend_color = "GREEN" if trend == "BULLISH" else "RED"
    consistency = sum(1 for c in colors if c == trend_color) / len(colors)
    if consistency < params.chop_dir_threshold:
        signals_fired.append(f"dir={consistency:.0%}")

    is_chop = len(signals_fired) >= 2
    return is_chop, " | ".join(signals_fired)


def has_large_fvg(candles: list[dict], trend: str, params: StrategyParams) -> bool:
    avg = avg_body_size(candles, params.avg_body_lookback)
    limit = avg * params.large_fvg_body_mult
    for i in range(-8, -3):
        c1 = candles[i]
        c3 = candles[i + 2]
        if trend == "BULLISH":
            if (c3["open"] - c1["high"]) > limit:
                return True
        elif trend == "BEARISH":
            if (c1["low"] - c3["open"]) > limit:
                return True
    return False


def has_post_impulse(candles: list[dict], params: StrategyParams) -> tuple[bool, str]:
    avg = avg_body_size(candles, params.avg_body_lookback)
    pre_signal = candles[-3]
    if body(pre_signal) > avg * params.post_impulse_mult:
        ratio = body(pre_signal) / avg
        return True, f"prev_body={ratio:.1f}x_avg"
    return False, ""


def is_late_entry(candles: list[dict], trend: str, params: StrategyParams) -> tuple[bool, str]:
    avg = avg_body_size(candles, params.avg_body_lookback)
    forming = candles[-1]
    limit = avg * params.late_entry_mult

    if trend == "BULLISH":
        move = forming["close"] - forming["open"]
    else:
        move = forming["open"] - forming["close"]

    if move > limit:
        pct = move / avg
        return True, f"forming_moved={pct:.1f}x_avg"
    return False, ""
