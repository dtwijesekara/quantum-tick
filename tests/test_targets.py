import pytest

from tests.conftest import candle
from quantum_tick.domain.models import StrategyParams
from quantum_tick.domain.targets import estimate_duration, find_nearest_swing

PARAMS = StrategyParams()


def test_estimate_duration_clamped_to_range():
    candles = [candle(100, 101, 99, 100.5, i * 60) for i in range(7)]  # avg body ~0.5
    # distance 50 / avg~0.5 = 100 candles -> clamp to max 15
    assert estimate_duration(candles, distance=50, params=PARAMS) == PARAMS.max_duration_mins
    # distance ~0 -> clamp to min 1
    assert estimate_duration(candles, distance=0, params=PARAMS) == PARAMS.min_duration_mins


def test_find_nearest_swing_bullish_returns_a_high_above_price():
    s = PARAMS.swing_strength
    closed = [candle(100, 100.5, 99.5, 100, i * 60) for i in range(30)]
    peak_idx = 15
    closed[peak_idx] = candle(100, 110, 99.5, 105, peak_idx * 60)  # clear local high
    forming = candle(100, 100, 100, 100, 30 * 60)
    candles = closed + [forming]

    price, distance = find_nearest_swing(candles, "BULLISH", PARAMS)
    assert price >= candles[-2]["close"]
    assert distance == pytest.approx(price - candles[-2]["close"])
