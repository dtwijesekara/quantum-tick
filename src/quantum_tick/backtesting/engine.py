"""Bar-by-bar replay of the v8 strategy against real historical candles.

No-lookahead guarantee: at replay step k, the strategy only ever sees
candles[0:k+1], and the only filter that reads the last element
(candles[-1], the "still forming" candle) is `is_late_entry` -- which we
disable in backtest mode (there's no historical sub-candle tick data to
evaluate it against honestly). Entry executes at that candle's OPEN, so
every input to the trading decision was already fully closed by the time of
entry. See outcomes.py for the entry/expiry pricing rationale.

One open position per symbol at a time (after a signal fires, replay skips
ahead past its expiry before scanning again) -- this mirrors the live bot's
own constraint of not re-entering the same symbol mid-trade, though the live
bot additionally serializes *across* all symbols (only one position open
system-wide); this backtest evaluates each symbol's series independently, so
combined signal counts across symbols are an upper bound on live trade
frequency, not a prediction of it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from quantum_tick.backtesting.outcomes import TradeOutcome, score_signal
from quantum_tick.backtesting.payouts import PayoutTable, payout_ratio_for
from quantum_tick.domain.models import StrategyParams
from quantum_tick.domain.state import FiredCandleTracker
from quantum_tick.domain.strategy import evaluate_signal


def required_window(params: StrategyParams) -> int:
    return params.min_candles_needed() + 6  # mirrors dt_bot_v8's live per-scan candle_count buffer


@dataclass
class SymbolBacktestResult:
    symbol: str
    outcomes: list[TradeOutcome] = field(default_factory=list)
    techniques: list[str] = field(default_factory=list)  # parallel to `outcomes`
    skip_counts: dict[str, int] = field(default_factory=dict)


def run_symbol_backtest(
    symbol: str,
    candles: list[dict],
    params: StrategyParams,
    payout_table: PayoutTable,
) -> SymbolBacktestResult:
    result = SymbolBacktestResult(symbol=symbol)
    tracker = FiredCandleTracker()
    window = required_window(params)
    n = len(candles)

    k = params.min_candles_needed()
    while k < n - 1:
        start = max(0, k + 1 - window)
        window_slice = candles[start : k + 1]

        eval_result = evaluate_signal(window_slice, symbol, params, tracker, check_late_entry=False)

        if eval_result.skip_reason:
            result.skip_counts[eval_result.skip_reason] = result.skip_counts.get(eval_result.skip_reason, 0) + 1
            k += 1
            continue

        signal = eval_result.signal
        tracker.mark_fired(symbol, window_slice)

        payout_ratio = payout_ratio_for(payout_table, symbol, signal.duration_mins)
        outcome = score_signal(candles, k, signal.contract_type, signal.duration_mins, payout_ratio)

        if outcome is None:
            k += 1  # not enough trailing history to score (tail of dataset); just advance
            continue

        result.outcomes.append(outcome)
        result.techniques.append("+".join(signal.entries))
        k += signal.duration_mins  # one open position per symbol at a time

    return result


def run_backtest(
    candles_by_symbol: dict[str, list[dict]],
    params: StrategyParams,
    payout_table: PayoutTable,
) -> dict[str, SymbolBacktestResult]:
    return {
        symbol: run_symbol_backtest(symbol, candles, params, payout_table)
        for symbol, candles in candles_by_symbol.items()
    }
