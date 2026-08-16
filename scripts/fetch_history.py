"""Fetch and cache real historical candles for every configured symbol.

Paginates past Deriv's silent 1000-candle-per-request cap (see
docs/postmortem/PROJECT_POSTMORTEM.md item 8) and logs the *actual* number
of candles received per page, not just what was requested -- a silent
truncation should never pass unnoticed.

Usage: python scripts/fetch_history.py [--days 60]
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from quantum_tick.config import get_settings  # noqa: E402
from quantum_tick.infrastructure.deriv.auth import AccountBootstrap  # noqa: E402
from quantum_tick.infrastructure.deriv.client import DerivClient  # noqa: E402
from quantum_tick.infrastructure.deriv.historical import fetch_history  # noqa: E402
from quantum_tick.logging_setup import setup_logging  # noqa: E402
from quantum_tick.persistence.db import make_session_factory  # noqa: E402
from quantum_tick.persistence.repository import CandleRepository  # noqa: E402

log = setup_logging("quantum_tick", "logs/fetch_history.log")


async def main(days: int) -> None:
    settings = get_settings()
    granularity = settings.timeframe_seconds
    total_needed = days * 24 * 60 * 60 // granularity

    bootstrap = AccountBootstrap(
        app_id=settings.deriv_app_id,
        api_token=settings.deriv_api_token,
        account_type=settings.deriv_account_type,
        currency=settings.deriv_currency,
    )
    ws_url = await bootstrap.get_websocket_url()

    session_factory = make_session_factory(settings.database_url)
    repo = CandleRepository(session_factory)

    async with DerivClient(ws_url) as client:
        for symbol in settings.symbol_list:
            already = repo.count(symbol, granularity)
            log.info(f"[{symbol}] cached={already}  target={total_needed}  fetching...")

            candles = await fetch_history(client, symbol, granularity, total_needed)
            inserted = repo.upsert_many(symbol, granularity, candles)

            total_now = repo.count(symbol, granularity)
            log.info(f"[{symbol}] fetched={len(candles)}  inserted_new={inserted}  total_cached={total_now}")

            if len(candles) < total_needed:
                log.warning(f"[{symbol}] only {len(candles)}/{total_needed} candles available "
                            f"(instrument history may not go back {days} days)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=60)
    args = parser.parse_args()
    asyncio.run(main(args.days))
