import pytest

from quantum_tick.backtesting.outcomes import TradeOutcome
from quantum_tick.backtesting.position_sizing import simulate_flat_stake, simulate_martingale


def _outcome(won: bool, payout_ratio: float = 0.9) -> TradeOutcome:
    return TradeOutcome(
        entry_open_time=0, entry_price=100, expiry_price=101 if won else 99,
        contract_type="CALL", duration_mins=1, payout_ratio=payout_ratio,
        outcome="won" if won else "lost", pnl=payout_ratio if won else -1.0,
    )


def test_flat_stake_hand_verified_wlwl_sequence():
    # W(+0.9) L(-1) W(+0.9) L(-1), stake=1 -> cumulative: 0.9, -0.1, 0.8, -0.2
    # peak stays 0.9 throughout; worst drawdown = 0.9 - (-0.2) = 1.1
    outcomes = [_outcome(True), _outcome(False), _outcome(True), _outcome(False)]
    result = simulate_flat_stake(outcomes, stake=1.0)
    assert result.final_pnl == pytest.approx(-0.2)
    assert result.max_drawdown == pytest.approx(1.1)


def test_martingale_doubles_after_each_loss_and_resets_on_win():
    # L L W: stake sequence 1, 2, 4 (win pays 4*0.9=3.6)
    # cumulative: -1, -3, +0.6 -> final_pnl=0.6, max_drawdown=3 (0 - (-3))
    outcomes = [_outcome(False), _outcome(False), _outcome(True)]
    result = simulate_martingale(outcomes, base_stake=1.0, multiplier=2.0)
    assert result.final_pnl == pytest.approx(0.6)
    assert result.max_drawdown == pytest.approx(3.0)
    assert result.peak_stake_required == pytest.approx(4.0)
    assert result.max_consecutive_losses_before_recovery == 2
    assert result.ruin_index is None


def test_martingale_stops_at_ruin_bankroll_instead_of_going_negative():
    # L L L with ruin_bankroll=3: trade0 stake=1 (ok), trade1 stake=2 (ok),
    # trade2 would need stake=4 > 3 -> ruin at index 2, that trade never executes
    outcomes = [_outcome(False), _outcome(False), _outcome(False)]
    result = simulate_martingale(outcomes, base_stake=1.0, multiplier=2.0, ruin_bankroll=3.0)
    assert result.ruin_index == 2
    assert result.peak_stake_required == pytest.approx(4.0)  # the stake that *would* have been needed
    assert result.final_pnl == pytest.approx(-3.0)  # only the first two losing trades executed


def test_martingale_with_no_losses_never_exceeds_base_stake():
    outcomes = [_outcome(True) for _ in range(5)]
    result = simulate_martingale(outcomes, base_stake=1.0, multiplier=2.0)
    assert result.peak_stake_required == pytest.approx(1.0)
    assert result.max_consecutive_losses_before_recovery == 0
