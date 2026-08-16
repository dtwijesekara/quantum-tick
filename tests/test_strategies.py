from tests.conftest import candle

from quantum_tick.domain.strategies import BreakoutStrategy, RandomStrategy, V8Strategy
from quantum_tick.domain.strategies.base import DetectedSignal


def test_breakout_strategy_wraps_detect_breakout():
    window = [candle(100, 105, 95, 100, i * 60) for i in range(20)]
    signal = candle(100, 108, 100, 107, 20 * 60)  # closes above the 105 channel high
    forming = candle(107, 107, 107, 107, 21 * 60)
    candles = window + [signal, forming]

    strategy = BreakoutStrategy(channel_lookback=20, duration_mins=5)
    result = strategy.detect(candles, "R_10")

    assert result == DetectedSignal(contract_type="CALL", duration_mins=5, technique="breakout")


def test_breakout_strategy_none_when_no_breakout():
    window = [candle(100, 105, 95, 100, i * 60) for i in range(20)]
    signal = candle(100, 102, 98, 101, 20 * 60)
    forming = candle(101, 101, 101, 101, 21 * 60)
    candles = window + [signal, forming]

    strategy = BreakoutStrategy(channel_lookback=20, duration_mins=5)
    assert strategy.detect(candles, "R_10") is None


def test_random_strategy_is_reproducible_with_same_seed():
    candles = [candle(100, 101, 99, 100, i * 60) for i in range(5)]

    a = RandomStrategy(seed=7, duration_mins=2)
    b = RandomStrategy(seed=7, duration_mins=2)

    results_a = [a.detect(candles, "R_10") for _ in range(20)]
    results_b = [b.detect(candles, "R_10") for _ in range(20)]
    assert results_a == results_b


def test_random_strategy_always_fires_at_fire_probability_one():
    candles = [candle(100, 101, 99, 100, i * 60) for i in range(5)]
    strategy = RandomStrategy(seed=1, fire_probability=1.0, duration_mins=3)

    for _ in range(50):
        result = strategy.detect(candles, "R_10")
        assert result is not None
        assert result.contract_type in ("CALL", "PUT")
        assert result.duration_mins == 3


def test_random_strategy_never_fires_at_fire_probability_zero():
    candles = [candle(100, 101, 99, 100, i * 60) for i in range(5)]
    strategy = RandomStrategy(seed=1, fire_probability=0.0)
    for _ in range(20):
        assert strategy.detect(candles, "R_10") is None


def test_v8_strategy_returns_none_on_insufficient_data():
    strategy = V8Strategy()
    tiny_candles = [candle(100, 101, 99, 100, i * 60) for i in range(5)]
    assert strategy.detect(tiny_candles, "R_10") is None
