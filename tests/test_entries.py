from tests.conftest import candle

from quantum_tick.domain.entries import detect_entry
from quantum_tick.domain.models import StrategyParams

PARAMS = StrategyParams()


def test_engulfing_fires_when_bullish_candle_covers_prior_red():
    # avg body over candles[-6:-1] = bodies [1,1,1,1,3] = 1.4 (hand-computed,
    # see docs/postmortem/PROJECT_POSTMORTEM.md item 12).
    normal = [candle(100, 101, 99, 101, i * 60) for i in range(5)]  # body 1 each
    prev = candle(100, 100.2, 98, 98, 5 * 60)  # RED, body 2
    curr = candle(97.5, 100.6, 97.4, 100.5, 6 * 60)  # GREEN, body 3, covers prev fully
    forming = candle(100.5, 100.5, 100.5, 100.5, 7 * 60)
    candles = normal + [prev, curr, forming]

    entries = detect_entry(candles, "BULLISH", PARAMS)
    assert "ENGULFING" in entries


def test_hop_fires_on_gap_down_open_without_engulfing_a_green_prev():
    # gap = prev.close(101) - curr.open(100.5) = 0.5
    # avg body over candles[-6:-1] = bodies [1,1,1,1,0.8] = 0.96 -> min_gap=0.096
    # 0.5 >= 0.096 -> HOP fires. prev is GREEN so bullish ENGULFING can't fire.
    normal = [candle(100, 101, 99, 101, i * 60) for i in range(3)]  # body 1 each
    prev = candle(100, 101.1, 99.9, 101, 3 * 60)  # GREEN, body 1
    curr = candle(100.5, 101.4, 100.4, 101.3, 4 * 60)  # GREEN, body 0.8, gapped down open
    forming = candle(101.3, 101.3, 101.3, 101.3, 5 * 60)
    candles = normal + [prev, curr, forming]

    entries = detect_entry(candles, "BULLISH", PARAMS)
    assert entries == ["HOP"]


def test_no_entry_when_neither_pattern_present():
    # true dojis (open == close): zero body means no gap between consecutive
    # opens/closes, so neither ENGULFING nor HOP's coverage/gap math can fire.
    flat = [candle(100, 100.1, 99.9, 100, i * 60) for i in range(8)]
    assert detect_entry(flat, "BULLISH", PARAMS) == []
