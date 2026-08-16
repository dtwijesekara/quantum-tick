import pytest

from quantum_tick.research.statistics import autocorrelation, pearson_correlation, runs_test


def test_autocorrelation_lag1_hand_verified_alternating_series():
    # series = [1,-1,1,-1,1,-1], mean=0, deviations = series itself.
    # numerator = sum of consecutive products = -1 five times = -5
    # denominator = sum of squares = 6
    # autocorr = -5/6 (hand-computed per docs/postmortem/... item 12's
    # standing rule: verify multi-term arithmetic before trusting it).
    series = [1, -1, 1, -1, 1, -1]
    assert autocorrelation(series, lag=1) == pytest.approx(-5 / 6)


def test_autocorrelation_zero_variance_series_returns_zero_not_nan():
    assert autocorrelation([5, 5, 5, 5, 5], lag=1) == 0.0


def test_runs_test_hand_verified_perfectly_alternating_sequence():
    # 10 True / 10 False, perfectly alternating -> runs=20 (every element
    # differs from its neighbor), far more than the ~11 expected by chance.
    # expected = 2*10*10/20 + 1 = 11
    # variance = 2*10*10*(200-20) / (20^2 * 19) = 36000/7600 = 4.7368...
    # z = (20-11)/sqrt(4.7368) = 4.134 (hand-computed)
    seq = [i % 2 == 0 for i in range(20)]
    result = runs_test(seq)
    assert result.runs == 20
    assert result.expected_runs == pytest.approx(11.0)
    assert result.z == pytest.approx(4.134, abs=0.01)
    assert result.p_value < 0.001  # far too many alternations to be random


def test_runs_test_single_run_is_extremely_non_random():
    seq = [True] * 10 + [False] * 10
    result = runs_test(seq)
    assert result.runs == 2
    assert result.z < -3  # far fewer runs than chance would produce


def test_pearson_correlation_perfect_positive():
    x = [1.0, 2.0, 3.0, 4.0, 5.0]
    y = [2.0, 4.0, 6.0, 8.0, 10.0]
    result = pearson_correlation(x, y)
    assert result.r == pytest.approx(1.0)
    assert result.p_value < 0.01


def test_pearson_correlation_perfect_negative():
    x = [1.0, 2.0, 3.0, 4.0, 5.0]
    y = [10.0, 8.0, 6.0, 4.0, 2.0]
    result = pearson_correlation(x, y)
    assert result.r == pytest.approx(-1.0)


def test_pearson_correlation_constant_series_returns_zero_not_crash():
    x = [1.0, 1.0, 1.0, 1.0]
    y = [1.0, 2.0, 3.0, 4.0]
    result = pearson_correlation(x, y)
    assert result.r == 0.0
