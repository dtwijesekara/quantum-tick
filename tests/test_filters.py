from tests.conftest import candle

from quantum_tick.domain.filters import (
    detect_bos_choch,
    detect_trend,
    has_large_fvg,
    has_post_impulse,
    is_choppy_market,
    is_late_entry,
)
from quantum_tick.domain.models import StrategyParams

PARAMS = StrategyParams()


def _candles_from_colors(colors: str, epoch_start: int = 0) -> list[dict]:
    """`colors` like "RGRRGGGG" -> one candle per char, oldest first, plus
    one trailing placeholder candle (detect_trend's window excludes the very
    last list element)."""
    out = []
    for i, c in enumerate(colors):
        if c == "G":
            out.append(candle(100, 101.2, 99.9, 101, epoch_start + i * 60))
        else:
            out.append(candle(100, 100.1, 98.8, 99, epoch_start + i * 60))
    out.append(candle(100, 100, 100, 100, epoch_start + len(colors) * 60))  # placeholder, excluded
    return out


def test_detect_trend_fires_bullish_on_a_clean_run():
    # last 4 candles green (run=4), within [trend_min=3, trend_max=5]
    candles = _candles_from_colors("RGRRGGGG")
    trend, reason = detect_trend(candles, PARAMS)
    assert trend == "BULLISH"
    assert reason is None


def test_detect_trend_rejects_short_run_as_no_trend():
    # only 2 green at the end -- below trend_min=3
    candles = _candles_from_colors("RGRGRRGG")
    trend, reason = detect_trend(candles, PARAMS)
    assert trend is None
    assert reason == "no_trend"


def test_detect_trend_flags_exhaustion_past_max_run():
    # 6 consecutive green at the end -- above trend_max=5
    candles = _candles_from_colors("RRGGGGGG")
    trend, reason = detect_trend(candles, PARAMS)
    assert trend is None
    assert reason == "exhaustion"


def test_detect_bos_choch_requires_close_beyond_swing():
    window = [candle(100, 105, 95, 100, i * 60) for i in range(17)]
    current = candle(100, 110, 100, 106, 17 * 60)  # closes above the 105 swing high
    forming = candle(106, 106, 106, 106, 18 * 60)
    candles = window + [current, forming]
    structure = detect_bos_choch(candles, "BULLISH", PARAMS)
    assert structure in ("BOS", "CHoCH")


def test_detect_bos_choch_none_when_close_stays_inside_range():
    window = [candle(100, 105, 95, 100, i * 60) for i in range(17)]
    current = candle(100, 102, 98, 101, 17 * 60)  # doesn't clear the 105 swing high
    forming = candle(101, 101, 101, 101, 18 * 60)
    candles = window + [current, forming]
    assert detect_bos_choch(candles, "BULLISH", PARAMS) is None


def test_is_choppy_market_flags_alternating_small_bodies():
    colors = "GRGRGRGR"  # 100% alternation -> exceeds 60% threshold
    candles = []
    for i, c in enumerate(colors):
        if c == "G":
            candles.append(candle(100, 100.3, 99.9, 100.2, i * 60))
        else:
            candles.append(candle(100, 100.1, 99.7, 99.8, i * 60))
    candles.append(candle(100, 100, 100, 100, len(colors) * 60))  # excluded "current" element
    is_chop, reason = is_choppy_market(candles, "BULLISH", PARAMS)
    assert is_chop is True
    assert "alternation" in reason


def test_has_large_fvg_true_for_gap_beyond_threshold():
    base = [candle(100, 101, 99, 100, i * 60) for i in range(5)]  # avg body ~1
    # candles[-8] and candles[-6] straddle a gap of 10 (>> 2x avg body of ~1)
    gap_c1 = candle(100, 100, 99, 100, 5 * 60)
    gap_c2 = candle(105, 106, 104, 105, 6 * 60)
    gap_c3 = candle(115, 116, 114, 115, 7 * 60)  # opens 10 above c1's high
    tail = [candle(115, 116, 114, 115, i * 60) for i in range(8, 11)]
    candles = base + [gap_c1, gap_c2, gap_c3] + tail
    assert has_large_fvg(candles, "BULLISH", PARAMS) is True


def test_has_post_impulse_true_for_oversized_prior_candle():
    normal = [candle(100, 101, 99, 100.5, i * 60) for i in range(5)]  # body 0.5 each
    impulse = candle(100, 108, 100, 108, 5 * 60)  # body 8, way > 2.5x avg (~0.5)
    signal = candle(108, 108.5, 106, 106.5, 6 * 60)
    forming = candle(106.5, 107, 106, 106.8, 7 * 60)
    candles = normal + [impulse, signal, forming]
    is_impulse, detail = has_post_impulse(candles, PARAMS)
    assert is_impulse is True
    assert "x_avg" in detail


def test_is_late_entry_true_when_forming_candle_already_moved_far():
    normal = [candle(100, 101, 99, 100.2, i * 60) for i in range(5)]  # body ~0.2
    signal = candle(100, 100.5, 99.8, 100.3, 5 * 60)
    forming = candle(100.3, 101.5, 100.3, 101.5, 6 * 60)  # moved 1.2, >> 1.5x avg(~0.2)=0.3
    candles = normal + [signal, forming]
    is_late, detail = is_late_entry(candles, "BULLISH", PARAMS)
    assert is_late is True
    assert "x_avg" in detail
