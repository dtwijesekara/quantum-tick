from tests.conftest import candle

from quantum_tick.domain.breakout import detect_breakout


def test_call_when_signal_closes_above_channel_high():
    # channel window = candles[-22:-2], highest high in it = 105
    window = [candle(100, 105, 95, 100, i * 60) for i in range(20)]
    signal = candle(100, 108, 100, 107, 20 * 60)  # closes at 107 > 105
    forming = candle(107, 107, 107, 107, 21 * 60)
    candles = window + [signal, forming]
    assert detect_breakout(candles, channel_lookback=20) == "CALL"


def test_put_when_signal_closes_below_channel_low():
    window = [candle(100, 105, 95, 100, i * 60) for i in range(20)]
    signal = candle(100, 100, 90, 92, 20 * 60)  # closes at 92 < 95
    forming = candle(92, 92, 92, 92, 21 * 60)
    candles = window + [signal, forming]
    assert detect_breakout(candles, channel_lookback=20) == "PUT"


def test_none_when_signal_stays_inside_channel():
    window = [candle(100, 105, 95, 100, i * 60) for i in range(20)]
    signal = candle(100, 102, 98, 101, 20 * 60)
    forming = candle(101, 101, 101, 101, 21 * 60)
    candles = window + [signal, forming]
    assert detect_breakout(candles, channel_lookback=20) is None


def test_none_when_not_enough_history():
    window = [candle(100, 105, 95, 100, i * 60) for i in range(5)]
    signal = candle(100, 108, 100, 107, 5 * 60)
    forming = candle(107, 107, 107, 107, 6 * 60)
    candles = window + [signal, forming]
    assert detect_breakout(candles, channel_lookback=20) is None
