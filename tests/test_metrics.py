import pytest

from quantum_tick.backtesting.metrics import compute_stats, max_streak, split_in_out_sample
from quantum_tick.backtesting.outcomes import TradeOutcome


def _outcome(won: bool, payout_ratio: float = 0.85) -> TradeOutcome:
    return TradeOutcome(
        entry_open_time=0,
        entry_price=100,
        expiry_price=101 if won else 99,
        contract_type="CALL",
        duration_mins=1,
        payout_ratio=payout_ratio,
        outcome="won" if won else "lost",
        pnl=payout_ratio if won else -1.0,
    )


def test_compute_stats_returns_none_for_empty_input():
    assert compute_stats([]) is None


def test_breakeven_rate_matches_the_real_payout_ratio_not_50_percent():
    # payout_ratio 0.85 -> breakeven win rate = 1/(1+0.85) = 0.540540...
    # (docs/postmortem/PROJECT_POSTMORTEM.md Checklist B item 3)
    outcomes = [_outcome(won=True, payout_ratio=0.85) for _ in range(54)] + \
               [_outcome(won=False, payout_ratio=0.85) for _ in range(46)]
    stats = compute_stats(outcomes)
    assert stats.breakeven_rate == pytest.approx(1 / 1.85, rel=1e-9)
    assert stats.win_rate == pytest.approx(0.54)


def test_edge_is_win_rate_minus_breakeven():
    outcomes = [_outcome(won=True) for _ in range(60)] + [_outcome(won=False) for _ in range(40)]
    stats = compute_stats(outcomes)
    assert stats.edge == pytest.approx(stats.win_rate - stats.breakeven_rate)


def test_significance_requires_positive_edge_not_just_a_low_p_value():
    # a large, consistent LOSS also produces a tiny p-value -- must not be
    # reported as a significant *edge*.
    outcomes = [_outcome(won=True) for _ in range(20)] + [_outcome(won=False) for _ in range(80)]
    stats = compute_stats(outcomes)
    assert stats.p_value < 0.05
    assert stats.edge < 0
    assert stats.significant is False


def test_max_streak_finds_longest_consecutive_run_anywhere_in_sequence():
    # W L L L W W L L  -> longest loss streak = 3, longest win streak = 2
    seq = [True, False, False, False, True, True, False, False]
    outcomes = [_outcome(won=w) for w in seq]
    assert max_streak(outcomes, "lost") == 3
    assert max_streak(outcomes, "won") == 2


def test_max_streak_zero_when_kind_never_occurs():
    outcomes = [_outcome(won=True) for _ in range(5)]
    assert max_streak(outcomes, "lost") == 0


def test_split_in_out_sample_is_chronological_not_shuffled():
    outcomes = [_outcome(won=(i % 2 == 0)) for i in range(10)]
    in_s, out_s = split_in_out_sample(outcomes, in_sample_fraction=0.7)
    assert len(in_s) == 7
    assert len(out_s) == 3
    assert in_s == outcomes[:7]
    assert out_s == outcomes[7:]
