"""Statistics for judging a backtest, per
docs/postmortem/PROJECT_POSTMORTEM.md Checklist B:
  - breakeven line from the *actual* payout ratio, not 50%  (item 3)
  - in-sample vs out-of-sample, split chronologically per symbol (item 2)
  - a significance test, so a 51%-vs-50.8% "edge" isn't mistaken for a real one
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from quantum_tick.backtesting.outcomes import TradeOutcome


@dataclass(frozen=True)
class SampleStats:
    n: int
    wins: int
    win_rate: float
    breakeven_rate: float
    edge: float  # win_rate - breakeven_rate
    z: float
    p_value: float
    total_pnl: float

    @property
    def significant(self) -> bool:
        # two-sided, 95% confidence, AND the edge must be positive (not just
        # "significantly different from breakeven" -- could be significantly worse)
        return self.p_value < 0.05 and self.edge > 0


def _normal_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def compute_stats(outcomes: list[TradeOutcome]) -> SampleStats | None:
    n = len(outcomes)
    if n == 0:
        return None

    wins = sum(1 for o in outcomes if o.outcome == "won")
    win_rate = wins / n
    total_pnl = sum(o.pnl for o in outcomes)

    # per-trade payout ratio -> breakeven win rate p0 solves p0*r - (1-p0) = 0
    ratios = [o.pnl for o in outcomes if o.outcome == "won"]
    avg_ratio = (sum(ratios) / len(ratios)) if ratios else 0.0
    breakeven_rate = 1 / (1 + avg_ratio) if avg_ratio > 0 else 1.0

    # one-sample binomial z-test of win_rate vs breakeven_rate
    p0 = breakeven_rate
    se = math.sqrt(p0 * (1 - p0) / n) if 0 < p0 < 1 else 0.0
    z = (win_rate - p0) / se if se > 0 else 0.0
    p_value = 2 * (1 - _normal_cdf(abs(z)))

    return SampleStats(
        n=n,
        wins=wins,
        win_rate=win_rate,
        breakeven_rate=breakeven_rate,
        edge=win_rate - breakeven_rate,
        z=z,
        p_value=p_value,
        total_pnl=total_pnl,
    )


def max_streak(outcomes: list[TradeOutcome], outcome_kind: str = "lost") -> int:
    """Longest run of consecutive `outcome_kind` results, in chronological
    order. Computed over the *full* trade sequence, not a single in/out-of-
    sample split -- a running bot experiences a losing streak continuously
    regardless of where a stats split happens to fall, and the split can
    otherwise hide a streak that straddles the boundary."""

    best = current = 0
    for o in outcomes:
        if o.outcome == outcome_kind:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best


def split_in_out_sample(outcomes: list[TradeOutcome], in_sample_fraction: float = 0.7) -> tuple[list[TradeOutcome], list[TradeOutcome]]:
    """Chronological split (outcomes must already be time-ordered) -- a
    random split would leak information across the in/out-of-sample boundary
    since consecutive signals share overlapping candle windows."""

    n = len(outcomes)
    cut = int(n * in_sample_fraction)
    return outcomes[:cut], outcomes[cut:]
