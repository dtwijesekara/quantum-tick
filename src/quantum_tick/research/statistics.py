"""General-purpose statistical tests for edge-hunting research, separate
from the live trading path (domain/backtesting). Mirrors the methodology in
docs/research/RESEARCH_FINDINGS.md: autocorrelation, a runs test for
direction independence, and cross-series correlation -- each with a
significance test so a small numeric wobble isn't mistaken for a real
signal.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


def _normal_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def two_sided_p_from_z(z: float) -> float:
    return 2 * (1 - _normal_cdf(abs(z)))


def autocorrelation(series: list[float], lag: int) -> float:
    """Lag-k autocorrelation of a numeric series (e.g. returns)."""
    n = len(series)
    if lag <= 0 or lag >= n:
        raise ValueError("lag must be in [1, len(series)-1]")

    mean = sum(series) / n
    deviations = [x - mean for x in series]
    denom = sum(d * d for d in deviations)
    if denom == 0:
        return 0.0
    numer = sum(deviations[t] * deviations[t + lag] for t in range(n - lag))
    return numer / denom


@dataclass(frozen=True)
class RunsTestResult:
    n1: int
    n2: int
    runs: int
    expected_runs: float
    z: float
    p_value: float


def runs_test(binary_series: list[bool]) -> RunsTestResult:
    """Wald-Wolfowitz runs test: tests whether a binary sequence (e.g.
    up/down candle direction) is independent draws vs. having runs that are
    too long or too short to be random."""

    n1 = sum(1 for b in binary_series if b)
    n2 = len(binary_series) - n1
    n = n1 + n2

    runs = 1
    for i in range(1, n):
        if binary_series[i] != binary_series[i - 1]:
            runs += 1

    expected_runs = (2 * n1 * n2) / n + 1
    variance_numer = 2 * n1 * n2 * (2 * n1 * n2 - n)
    variance_denom = n * n * (n - 1)
    variance = variance_numer / variance_denom if variance_denom > 0 else 0.0

    z = (runs - expected_runs) / math.sqrt(variance) if variance > 0 else 0.0
    return RunsTestResult(
        n1=n1, n2=n2, runs=runs, expected_runs=expected_runs,
        z=z, p_value=two_sided_p_from_z(z),
    )


@dataclass(frozen=True)
class CorrelationResult:
    n: int
    r: float
    t: float
    p_value: float


def pearson_correlation(x: list[float], y: list[float]) -> CorrelationResult:
    n = len(x)
    if n != len(y):
        raise ValueError("x and y must be the same length")
    if n < 3:
        raise ValueError("need at least 3 points")

    mean_x = sum(x) / n
    mean_y = sum(y) / n
    cov = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
    var_x = sum((xi - mean_x) ** 2 for xi in x)
    var_y = sum((yi - mean_y) ** 2 for yi in y)

    denom = math.sqrt(var_x * var_y)
    r = cov / denom if denom > 0 else 0.0

    # t-distribution ~ normal for the sample sizes used here (tens of
    # thousands of candles), so the normal approximation is used for p.
    if abs(r) >= 1.0:
        t = float("inf") if r > 0 else float("-inf")
    else:
        t = r * math.sqrt(n - 2) / math.sqrt(1 - r * r)

    return CorrelationResult(n=n, r=r, t=t, p_value=two_sided_p_from_z(t))
