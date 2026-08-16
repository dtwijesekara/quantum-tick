import pytest

from tests.conftest import candle
from quantum_tick.backtesting.outcomes import score_signal


def test_expiry_candle_is_entry_idx_plus_duration_minus_one():
    # entry at idx0 (open=T), duration=3min -> expiry at T+180, which is the
    # CLOSE of the candle covering T+120..T+180, i.e. idx 0+3-1=2.
    # Hand-verified per docs/postmortem/PROJECT_POSTMORTEM.md item 12.
    candles = [
        candle(100, 101, 99, 100.5, epoch=0),    # idx0: entry candle, open=100
        candle(100.5, 102, 100, 101.5, epoch=60),  # idx1
        candle(101.5, 103, 101, 102.7, epoch=120),  # idx2: expiry candle, close=102.7
        candle(102.7, 104, 102, 103, epoch=180),   # idx3: irrelevant, after expiry
    ]
    outcome = score_signal(candles, entry_idx=0, contract_type="CALL", duration_mins=3, payout_ratio=0.85)

    assert outcome is not None
    assert outcome.entry_price == 100
    assert outcome.expiry_price == pytest.approx(102.7)
    assert outcome.outcome == "won"  # 102.7 > 100


def test_put_wins_when_price_falls():
    candles = [
        candle(100, 101, 99, 100, epoch=0),
        candle(100, 101, 95, 96, epoch=60),  # expiry candle (idx0+2-1=1), close=96
    ]
    outcome = score_signal(candles, entry_idx=0, contract_type="PUT", duration_mins=2, payout_ratio=0.9)
    assert outcome.outcome == "won"
    assert outcome.pnl == pytest.approx(0.9)


def test_loss_has_pnl_of_negative_one_stake():
    candles = [
        candle(100, 101, 99, 100, epoch=0),
        candle(100, 103, 99, 102, epoch=60),  # price rose -> PUT loses
    ]
    outcome = score_signal(candles, entry_idx=0, contract_type="PUT", duration_mins=2, payout_ratio=0.9)
    assert outcome.outcome == "lost"
    assert outcome.pnl == pytest.approx(-1.0)


def test_returns_none_when_not_enough_trailing_history():
    # duration=5 needs an expiry candle at idx 0+5-1=4, but only 2 candles exist
    candles = [candle(100, 101, 99, 100, epoch=0), candle(100, 101, 99, 100, epoch=60)]
    outcome = score_signal(candles, entry_idx=0, contract_type="CALL", duration_mins=5, payout_ratio=0.85)
    assert outcome is None
