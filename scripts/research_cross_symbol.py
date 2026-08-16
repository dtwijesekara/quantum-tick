"""Hypothesis: does one volatility index's return lead another's? Uses the
candle cache already built by fetch_history.py -- no new network calls.

For every symbol pair (A, B) and lag k in [-5..5] minutes, computes Pearson
correlation between A's return at t and B's return at t+k, Bonferroni-
corrected for the 10 pairs x 11 lags = 110 comparisons (otherwise ~5-6
would clear p<0.05 by chance alone even with no real relationship).

Usage: python scripts/research_cross_symbol.py
"""

import sys
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from quantum_tick.config import get_settings  # noqa: E402
from quantum_tick.persistence.db import make_session_factory  # noqa: E402
from quantum_tick.persistence.repository import CandleRepository  # noqa: E402
from quantum_tick.research.statistics import pearson_correlation  # noqa: E402

MAX_LAG = 5


def returns_by_epoch(candles: list[dict]) -> dict[int, float]:
    """Return keyed by the epoch of the *later* candle in each pair, so two
    symbols can be aligned by common epoch even when their fetch windows
    (and therefore raw list indices) don't line up minute-for-minute."""
    return {b["epoch"]: b["close"] - a["close"] for a, b in zip(candles, candles[1:])}


def aligned_series(a: dict[int, float], b: dict[int, float], lag: int) -> tuple[list[float], list[float]]:
    """x = symbol A's return at epoch e, y = symbol B's return at epoch e+lag*granularity.
    Only keeps epochs present in both, so this is robust to each symbol
    having a different, possibly gappy, set of cached epochs."""
    xs, ys = [], []
    for epoch, x_val in a.items():
        target_epoch = epoch + lag * 60
        if target_epoch in b:
            xs.append(x_val)
            ys.append(b[target_epoch])
    return xs, ys


def main() -> None:
    settings = get_settings()
    session_factory = make_session_factory(settings.database_url)
    repo = CandleRepository(session_factory)
    granularity = settings.timeframe_seconds

    series = {}
    for symbol in settings.symbol_list:
        candles = repo.load(symbol, granularity)
        series[symbol] = returns_by_epoch(candles)
        print(f"[{symbol}] {len(candles)} candles cached, epoch range "
              f"{candles[0]['epoch']}..{candles[-1]['epoch']}")

    pairs = list(combinations(settings.symbol_list, 2))
    n_tests = len(pairs) * (2 * MAX_LAG + 1)
    bonferroni_alpha = 0.05 / n_tests
    print(f"\nTesting {len(pairs)} pairs x {2*MAX_LAG+1} lags = {n_tests} correlations, "
          f"aligned by shared epoch (lag in minutes, A leads B when lag>0).")
    print(f"Bonferroni-corrected significance threshold: p < {bonferroni_alpha:.6f}\n")

    print(f"{'Pair':<16} {'Lag':>4} {'N':>7} {'r':>9} {'p-value':>12} {'Bonferroni-sig?':>16}")
    print("-" * 70)

    any_significant = False
    for sym_a, sym_b in pairs:
        for lag in range(-MAX_LAG, MAX_LAG + 1):
            x, y = aligned_series(series[sym_a], series[sym_b], lag)
            if len(x) < 1000:
                print(f"{sym_a}/{sym_b:<10} {lag:>4} {len(x):>7}  (too few shared epochs, skipped)")
                continue

            result = pearson_correlation(x, y)
            sig = result.p_value < bonferroni_alpha
            if sig:
                any_significant = True
                print(f"{sym_a}/{sym_b:<10} {lag:>4} {result.n:>7} {result.r:>9.4f} {result.p_value:>12.6f} {'YES':>16}")

    if not any_significant:
        print("(no pair/lag combination survived Bonferroni correction)")

    print("\nConclusion:", "at least one pair/lag shows a Bonferroni-significant "
          "cross-correlation -- worth a closer, out-of-sample look." if any_significant
          else "no evidence of cross-symbol lead-lag after correcting for the number "
               "of comparisons. Consistent with independently-generated index series.")


if __name__ == "__main__":
    main()
