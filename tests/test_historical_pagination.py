"""Verifies the `end`-parameter pagination boundary math against a fake
client -- Deriv silently caps ticks_history at 1000 candles/request (no
error), so this re-checks the exact claim from
docs/postmortem/PROJECT_POSTMORTEM.md item 8: adjacent pages join with no
overlap and no gap, rather than assuming it. Uses a fake client with a real
method surface, not None (item 14)."""

import pytest

from quantum_tick.infrastructure.deriv.historical import MAX_PAGE_SIZE, fetch_history


class FakeDerivClient:
    def __init__(self, all_candles: list[dict]):
        self._all = all_candles  # oldest-first

    async def request(self, payload: dict) -> dict:
        count = payload["count"]
        end = payload["end"]
        end_epoch = self._all[-1]["epoch"] if end == "latest" else int(end)
        eligible = [c for c in self._all if c["epoch"] <= end_epoch]
        return {"candles": eligible[-count:]}


def _synthetic_history(n: int, granularity: int = 60) -> list[dict]:
    return [
        {"open": 100, "high": 101, "low": 99, "close": 100, "epoch": i * granularity}
        for i in range(n)
    ]


@pytest.mark.asyncio
async def test_pagination_beyond_the_1000_cap_has_no_gap_or_overlap():
    all_candles = _synthetic_history(2500)
    client = FakeDerivClient(all_candles)

    result = await fetch_history(client, "R_10", granularity=60, total_count=2500)

    assert len(result) == 2500
    epochs = [c["epoch"] for c in result]
    assert epochs == sorted(epochs)
    assert len(set(epochs)) == len(epochs)  # no duplicates
    diffs = {b - a for a, b in zip(epochs, epochs[1:])}
    assert diffs == {60}  # exactly one candle-width between every pair, always
    assert epochs == [c["epoch"] for c in all_candles[-2500:]]


@pytest.mark.asyncio
async def test_single_page_request_stays_under_the_cap():
    all_candles = _synthetic_history(500)
    client = FakeDerivClient(all_candles)

    result = await fetch_history(client, "R_10", granularity=60, total_count=500)
    assert len(result) == 500


@pytest.mark.asyncio
async def test_requesting_more_than_available_history_stops_cleanly():
    all_candles = _synthetic_history(1500)
    client = FakeDerivClient(all_candles)

    result = await fetch_history(client, "R_10", granularity=60, total_count=5000)
    assert len(result) == 1500  # exhausted, no error, no infinite loop


def test_max_page_size_matches_derivs_documented_default():
    assert MAX_PAGE_SIZE == 1000
