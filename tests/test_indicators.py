import pytest

from quantum_tick.domain.indicators import ema, macd, rsi, sma


def test_sma_hand_verified():
    assert sma([1, 2, 3, 4, 5], period=3) == pytest.approx(4.0)  # avg(3,4,5)


def test_sma_none_when_not_enough_data():
    assert sma([1, 2], period=3) is None


def test_ema_hand_verified_linear_series():
    # series 1..10, period=3, k=0.5: seed=avg(1,2,3)=2, each subsequent EMA
    # of a +1 linear ramp with k=0.5 lags by exactly 1 -> converges to 9
    # when price=10 (hand-computed step by step, see PR description).
    series = list(range(1, 11))
    assert ema(series, period=3) == pytest.approx(9.0)


def test_ema_none_when_not_enough_data():
    assert ema([1, 2], period=5) is None


def test_rsi_hand_verified():
    # deltas: +0.5,-0.25,+0.25,+0.25,+0.25,+0.5
    # avg_gain=1.75/6, avg_loss=0.25/6 -> rs=1.75/0.25=7.0 exactly
    # rsi = 100 - 100/(1+7) = 87.5
    series = [44, 44.5, 44.25, 44.5, 44.75, 45.0, 45.5]
    assert rsi(series, period=6) == pytest.approx(87.5)


def test_rsi_100_when_no_losses():
    series = [1, 2, 3, 4, 5, 6, 7]
    assert rsi(series, period=6) == pytest.approx(100.0)


def test_rsi_none_when_not_enough_data():
    assert rsi([1, 2, 3], period=6) is None


def test_macd_hand_verified_linear_series():
    # Linear ramp 1..12, fast=3/slow=5/signal=2: both EMAs lag a linear
    # ramp by a constant offset, so the MACD line converges to a constant
    # (=1 here) and its own EMA (the signal line) converges to the same
    # constant -> histogram=0. Full derivation in the PR description.
    series = list(range(1, 13))
    result = macd(series, fast=3, slow=5, signal=2)
    assert result is not None
    macd_line, signal_line, histogram = result
    assert macd_line == pytest.approx(1.0)
    assert signal_line == pytest.approx(1.0)
    assert histogram == pytest.approx(0.0)


def test_macd_none_when_not_enough_data():
    assert macd([1, 2, 3], fast=12, slow=26, signal=9) is None
