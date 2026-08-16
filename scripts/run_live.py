"""Run the live bot. Defaults to DRY_RUN=true (logs what it would trade
without placing real orders) -- see .env / Settings.dry_run.

Usage: python scripts/run_live.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from quantum_tick.config import get_settings  # noqa: E402
from quantum_tick.domain.models import StrategyParams  # noqa: E402
from quantum_tick.logging_setup import setup_logging  # noqa: E402
from quantum_tick.persistence.db import make_session_factory  # noqa: E402
from quantum_tick.persistence.repository import LiveTradeRepository  # noqa: E402
from quantum_tick.services.live_trading_service import LiveTradingService  # noqa: E402

setup_logging("quantum_tick", "logs/quantum_tick.log")


async def main() -> None:
    settings = get_settings()
    session_factory = make_session_factory(settings.database_url)
    trade_repo = LiveTradeRepository(session_factory)

    service = LiveTradingService(settings, StrategyParams(), trade_repo)
    await service.run()


if __name__ == "__main__":
    asyncio.run(main())
