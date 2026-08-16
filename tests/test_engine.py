from tests.conftest import candle

from quantum_tick.backtesting.engine import run_backtest, run_symbol_backtest
from quantum_tick.backtesting.outcomes import TradeOutcome
from quantum_tick.domain.strategies.base import DetectedSignal


class AlwaysCallStrategy:
    """Fires CALL on every call -- used to check the engine's own bookkeeping
    (window sizing, skip-ahead-by-duration, technique passthrough) in
    isolation from any real strategy's decision logic."""

    name = "always_call"

    def __init__(self, duration_mins: int = 2):
        self.duration_mins = duration_mins
        self.required_window = 3
        self.calls = 0

    def detect(self, candles, symbol) -> DetectedSignal | None:
        self.calls += 1
        return DetectedSignal(contract_type="CALL", duration_mins=self.duration_mins, technique="always_call")


def _rising_candles(n: int) -> list[dict]:
    # strictly increasing close every candle -> every CALL should win
    return [candle(100 + i, 100 + i + 1, 100 + i - 0.5, 100 + i + 0.5, i * 60) for i in range(n)]


def test_engine_skips_ahead_by_duration_after_each_signal():
    candles = _rising_candles(50)
    strategy = AlwaysCallStrategy(duration_mins=5)

    result = run_symbol_backtest("R_10", candles, strategy, payout_table={})

    entry_times = [o.entry_open_time for o in result.outcomes]
    gaps = [b - a for a, b in zip(entry_times, entry_times[1:])]
    assert all(gap >= 5 * 60 for gap in gaps)  # no overlapping positions


def test_engine_passes_technique_through_to_outcome():
    candles = _rising_candles(30)
    strategy = AlwaysCallStrategy(duration_mins=3)

    result = run_symbol_backtest("R_10", candles, strategy, payout_table={})

    assert len(result.outcomes) > 0
    assert all(o.technique == "always_call" for o in result.outcomes)


def test_engine_scores_wins_correctly_on_a_rising_series():
    candles = _rising_candles(30)
    strategy = AlwaysCallStrategy(duration_mins=3)

    result = run_symbol_backtest("R_10", candles, strategy, payout_table={})

    assert len(result.outcomes) > 0
    assert all(o.outcome == "won" for o in result.outcomes)  # CALL on a strictly rising series always wins


def test_run_backtest_gives_each_symbol_a_fresh_strategy_instance():
    candles_by_symbol = {"R_10": _rising_candles(30), "R_25": _rising_candles(30)}

    results = run_backtest(candles_by_symbol, lambda: AlwaysCallStrategy(duration_mins=3), payout_table={})

    assert set(results.keys()) == {"R_10", "R_25"}
    assert isinstance(results["R_10"].outcomes[0], TradeOutcome)
