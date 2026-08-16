from tests.conftest import candle

from quantum_tick.domain.candles import avg_body_size, body, color, open_time


def test_color_uses_open_not_just_sign_of_close():
    # close > 0 alone doesn't tell you bullish/bearish -- open must be checked too
    # (docs/postmortem/PROJECT_POSTMORTEM.md item 13).
    bullish = candle(open_=10, high=12, low=9, close=11, epoch=0)
    bearish = candle(open_=12, high=13, low=9, close=11, epoch=0)
    assert color(bullish) == "GREEN"
    assert color(bearish) == "RED"


def test_body_is_absolute_distance():
    c = candle(open_=10, high=12, low=8, close=9, epoch=0)
    assert body(c) == 1


def test_open_time_prefers_open_time_field():
    c = {"open": 1, "high": 1, "low": 1, "close": 1, "epoch": 100, "open_time": 200}
    assert open_time(c) == 200


def test_open_time_falls_back_to_epoch_for_historical_snapshots():
    # Historical `candles` list entries only ever carry `epoch` -- see
    # docs/postmortem/PROJECT_POSTMORTEM.md item 7.
    c = {"open": 1, "high": 1, "low": 1, "close": 1, "epoch": 100}
    assert open_time(c) == 100


def test_avg_body_size_hand_verified():
    # Two candles with bodies 2 and 4 immediately before the excluded last
    # element -> average should be exactly 3, hand-computed before trusting
    # the fixture (docs/postmortem/PROJECT_POSTMORTEM.md item 12).
    candles = [
        candle(0, 5, 0, 2, epoch=0),   # body 2
        candle(0, 5, 0, 4, epoch=60),  # body 4
        candle(0, 5, 0, 0, epoch=120),  # excluded: this is the "current" candle
    ]
    assert avg_body_size(candles, lookback=2) == 3.0


def test_avg_body_size_skips_zero_body_candles():
    candles = [
        candle(5, 5, 5, 5, epoch=0),   # doji, body 0 -- excluded from average
        candle(0, 5, 0, 4, epoch=60),  # body 4
        candle(0, 5, 0, 0, epoch=120),
    ]
    assert avg_body_size(candles, lookback=2) == 4.0
