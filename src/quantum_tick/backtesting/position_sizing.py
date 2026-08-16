"""Flat-stake vs martingale position sizing, simulated over a real backtest
trade sequence.

Martingale does not create edge -- it cannot, since bet sizing is decided
before a trade's outcome is known and the outcome probabilities are
unchanged by it. It only reshapes variance: frequent small wins funded by
the risk of one bet large enough to erase them all. This module exists to
make that concrete against real observed loss streaks rather than assert it
abstractly -- see scripts/run_position_sizing_comparison.py.
"""

from __future__ import annotations

from dataclasses import dataclass

from quantum_tick.backtesting.outcomes import TradeOutcome


@dataclass(frozen=True)
class SizingResult:
    final_pnl: float
    max_drawdown: float  # largest peak-to-trough dip in cumulative pnl
    peak_stake_required: float
    max_consecutive_losses_before_recovery: int
    ruin_index: int | None  # trade index where required stake first exceeded `ruin_bankroll`, if any


def simulate_flat_stake(outcomes: list[TradeOutcome], stake: float = 1.0) -> SizingResult:
    cumulative = 0.0
    peak = 0.0
    max_drawdown = 0.0

    for o in outcomes:
        cumulative += stake * o.pnl  # o.pnl is already per-$1-stake (payout_ratio or -1)
        peak = max(peak, cumulative)
        max_drawdown = max(max_drawdown, peak - cumulative)

    return SizingResult(
        final_pnl=cumulative,
        max_drawdown=max_drawdown,
        peak_stake_required=stake,
        max_consecutive_losses_before_recovery=0,
        ruin_index=None,
    )


def simulate_martingale(
    outcomes: list[TradeOutcome],
    base_stake: float = 1.0,
    multiplier: float = 2.0,
    ruin_bankroll: float | None = None,
) -> SizingResult:
    """Classic martingale: stake resets to `base_stake` after a win and is
    multiplied by `multiplier` after each loss. `ruin_bankroll`, if given,
    is the largest stake the simulated trader could cover -- the first
    trade requiring more than that stops the simulation at `ruin_index`,
    matching what would really happen to an account of that size."""

    cumulative = 0.0
    peak = 0.0
    max_drawdown = 0.0
    stake = base_stake
    peak_stake = base_stake
    consecutive_losses = 0
    max_consecutive = 0
    ruin_index = None

    for i, o in enumerate(outcomes):
        peak_stake = max(peak_stake, stake)
        if ruin_bankroll is not None and stake > ruin_bankroll:
            ruin_index = i
            break

        cumulative += stake * o.pnl
        peak = max(peak, cumulative)
        max_drawdown = max(max_drawdown, peak - cumulative)

        if o.outcome == "lost":
            consecutive_losses += 1
            max_consecutive = max(max_consecutive, consecutive_losses)
            stake *= multiplier
        else:
            consecutive_losses = 0
            stake = base_stake

    return SizingResult(
        final_pnl=cumulative,
        max_drawdown=max_drawdown,
        peak_stake_required=peak_stake,
        max_consecutive_losses_before_recovery=max_consecutive,
        ruin_index=ruin_index,
    )
