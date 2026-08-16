"""Bar-by-bar replay for the Donchian breakout strategy (domain/breakout.py).

Same no-lookahead / one-open-position-per-symbol discipline as
backtesting/engine.py (which is v8-specific); kept separate rather than
generalizing both strategies behind a shared abstraction after only two
concrete cases -- see backtesting/engine.py for the v8 version's docstring
for the full no-lookahead rationale, which applies identically here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from quantum_tick.backtesting.outcomes import TradeOutcome, score_signal
from quantum_tick.backtesting.payouts import PayoutTable, payout_ratio_for
from quantum_tick.domain.breakout import detect_breakout


@dataclass
class BreakoutBacktestResult:
    symbol: str
    outcomes: list[TradeOutcome] = field(default_factory=list)


def run_breakout_backtest(
    symbol: str,
    candles: list[dict],
    channel_lookback: int,
    duration_mins: int,
    payout_table: PayoutTable,
) -> BreakoutBacktestResult:
    result = BreakoutBacktestResult(symbol=symbol)
    n = len(candles)
    min_needed = channel_lookback + 2

    k = min_needed
    while k < n - 1:
        window_slice = candles[max(0, k + 1 - (channel_lookback + 2)) : k + 1]
        contract_type = detect_breakout(window_slice, channel_lookback)

        if contract_type is None:
            k += 1
            continue

        payout_ratio = payout_ratio_for(payout_table, symbol, duration_mins)
        outcome = score_signal(candles, k, contract_type, duration_mins, payout_ratio)

        if outcome is None:
            k += 1
            continue

        result.outcomes.append(outcome)
        k += duration_mins  # one open position per symbol at a time

    return result
