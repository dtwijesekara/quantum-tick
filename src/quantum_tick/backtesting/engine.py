"""Bar-by-bar replay against real historical candles -- one engine shared by
every strategy (domain/strategies/*), not one per strategy. Previously v8
and breakout each had their own near-duplicate loop; adding a new strategy
now means writing a domain/strategies/*.py class, nothing here changes.

No-lookahead guarantee: at replay step k, a strategy only ever sees
candles[0:k+1]. v8's `is_late_entry` filter (the only filter that reads the
"still forming" last candle) is disabled in backtest mode -- there's no
historical sub-candle tick data to evaluate it against honestly. Entry
executes at that candle's OPEN, so every input to the trading decision was
already fully closed by the time of entry. See outcomes.py for the
entry/expiry pricing rationale.

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
from quantum_tick.domain.strategies.base import Strategy


@dataclass
class SymbolBacktestResult:
    symbol: str
    outcomes: list[TradeOutcome] = field(default_factory=list)


def run_symbol_backtest(
    symbol: str,
    candles: list[dict],
    strategy: Strategy,
    payout_table: PayoutTable,
) -> SymbolBacktestResult:
    result = SymbolBacktestResult(symbol=symbol)
    window = strategy.required_window
    n = len(candles)

    k = window
    while k < n - 1:
        window_slice = candles[max(0, k + 1 - window) : k + 1]

        detected = strategy.detect(window_slice, symbol)
        if detected is None:
            k += 1
            continue

        payout_ratio = payout_ratio_for(payout_table, symbol, detected.duration_mins)
        outcome = score_signal(
            candles, k, detected.contract_type, detected.duration_mins, payout_ratio, detected.technique
        )

        if outcome is None:
            k += 1  # not enough trailing history to score (tail of dataset); just advance
            continue

        result.outcomes.append(outcome)
        k += detected.duration_mins  # one open position per symbol at a time

    return result


def run_backtest(
    candles_by_symbol: dict[str, list[dict]],
    strategy_factory,
    payout_table: PayoutTable,
) -> dict[str, SymbolBacktestResult]:
    """`strategy_factory` is a zero-arg callable returning a *fresh*
    Strategy instance -- each symbol gets its own so per-symbol state (e.g.
    v8's same-candle lock) never leaks across symbols."""
    return {
        symbol: run_symbol_backtest(symbol, candles, strategy_factory(), payout_table)
        for symbol, candles in candles_by_symbol.items()
    }
