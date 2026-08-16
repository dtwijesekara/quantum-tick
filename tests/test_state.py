from tests.conftest import candle

from quantum_tick.domain.state import FiredCandleTracker


def test_fired_candle_tracker_blocks_repeat_fire_on_same_candle():
    candles = [candle(100, 101, 99, 100, epoch=0), candle(100, 101, 99, 100, epoch=60)]
    tracker = FiredCandleTracker()

    assert tracker.is_same_candle("R_10", candles) is False
    tracker.mark_fired("R_10", candles)
    assert tracker.is_same_candle("R_10", candles) is True


def test_fired_candle_tracker_is_per_symbol():
    candles = [candle(100, 101, 99, 100, epoch=0), candle(100, 101, 99, 100, epoch=60)]
    tracker = FiredCandleTracker()
    tracker.mark_fired("R_10", candles)
    assert tracker.is_same_candle("R_25", candles) is False


def test_fired_candle_tracker_unblocks_on_a_new_candle():
    tracker = FiredCandleTracker()
    first = [candle(100, 101, 99, 100, epoch=0), candle(100, 101, 99, 100, epoch=60)]
    tracker.mark_fired("R_10", first)

    later = [candle(100, 101, 99, 100, epoch=60), candle(100, 101, 99, 100, epoch=120)]
    assert tracker.is_same_candle("R_10", later) is False
