"""Paginated historical candle fetch.

Deriv silently caps `ticks_history` at 1000 candles per request (no error,
just truncation) -- see docs/postmortem/PROJECT_POSTMORTEM.md item 8. This
pages backward using `end = oldest_candle.open_time - granularity`, which
was verified empirically (in that prior project) to produce a clean,
non-overlapping, gap-free join between pages -- re-verified here by
tests/test_historical_pagination.py against a fake client.
"""

from __future__ import annotations

import logging

from quantum_tick.domain.candles import open_time
from quantum_tick.infrastructure.deriv.client import DerivClient

log = logging.getLogger("quantum_tick.deriv.historical")

MAX_PAGE_SIZE = 1000


async def fetch_history(
    client: DerivClient,
    symbol: str,
    granularity: int,
    total_count: int,
    end: str | int = "latest",
) -> list[dict]:
    """Fetch up to `total_count` most-recent closed candles, oldest-first."""

    all_candles: list[dict] = []
    cursor_end: str | int = end
    remaining = total_count

    while remaining > 0:
        page_size = min(remaining, MAX_PAGE_SIZE)
        resp = await client.request({
            "ticks_history": symbol,
            "end": str(cursor_end),
            "count": page_size,
            "style": "candles",
            "granularity": granularity,
        })
        page = resp.get("candles", [])
        if not page:
            break

        all_candles = page + all_candles
        remaining -= len(page)

        log.info("  [%s] fetched page: %d candles (requested %d, %d remaining)",
                  symbol, len(page), page_size, remaining)

        if len(page) < page_size:
            break  # exhausted available history

        cursor_end = open_time(page[0]) - granularity

    return all_candles
