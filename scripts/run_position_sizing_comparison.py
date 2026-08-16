"""Flat-stake vs martingale, simulated over the real breakout-strategy trade
sequence (scripts/run_backtest_breakout.py) -- the largest real sample this
project has. Martingale can't fix a lack of edge (it doesn't touch win
probability); this quantifies what it actually costs in real observed
streaks instead of asserting it.

Usage: python scripts/run_position_sizing_comparison.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from quantum_tick.backtesting.breakout_engine import run_breakout_backtest  # noqa: E402
from quantum_tick.backtesting.payouts import build_payout_table  # noqa: E402
from quantum_tick.backtesting.position_sizing import simulate_flat_stake, simulate_martingale  # noqa: E402
from quantum_tick.config import get_settings  # noqa: E402
from quantum_tick.infrastructure.deriv.auth import AccountBootstrap  # noqa: E402
from quantum_tick.infrastructure.deriv.client import DerivClient  # noqa: E402
from quantum_tick.persistence.db import make_session_factory  # noqa: E402
from quantum_tick.persistence.repository import CandleRepository  # noqa: E402

CHANNEL_LOOKBACK = 20
DURATION_MINS = 3
BASE_STAKE = 1.0
RUIN_BANKROLL = 1000.0  # a generously large hypothetical account, for illustration


async def main() -> None:
    settings = get_settings()
    granularity = settings.timeframe_seconds
    candle_repo = CandleRepository(make_session_factory(settings.database_url))

    bootstrap = AccountBootstrap(
        app_id=settings.deriv_app_id, api_token=settings.deriv_api_token,
        account_type=settings.deriv_account_type, currency=settings.deriv_currency,
    )
    ws_url = await bootstrap.get_websocket_url()
    async with DerivClient(ws_url) as client:
        payout_table = await build_payout_table(
            client, settings.symbol_list, durations=[DURATION_MINS],
            currency=settings.deriv_currency, stake=BASE_STAKE,
        )

    print(f"{'Symbol':<8} {'N':>6} {'Flat PnL':>10} {'Flat MaxDD':>11} "
          f"{'Mart. PnL':>10} {'Mart. MaxDD':>12} {'Peak stake':>12} {'Ruined?':>10}")
    print("-" * 90)

    for symbol in settings.symbol_list:
        candles = candle_repo.load(symbol, granularity)
        result = run_breakout_backtest(symbol, candles, CHANNEL_LOOKBACK, DURATION_MINS, payout_table)
        outcomes = result.outcomes

        flat = simulate_flat_stake(outcomes, stake=BASE_STAKE)
        mart = simulate_martingale(outcomes, base_stake=BASE_STAKE, multiplier=2.0, ruin_bankroll=RUIN_BANKROLL)

        ruined = f"YES @ trade {mart.ruin_index}" if mart.ruin_index is not None else "no"
        print(f"{symbol:<8} {len(outcomes):>6} {flat.final_pnl:>+10.2f} {flat.max_drawdown:>11.2f} "
              f"{mart.final_pnl:>+10.2f} {mart.max_drawdown:>12.2f} {mart.peak_stake_required:>12.2f} {ruined:>10}")

    print(f"\n(martingale simulated with base stake ${BASE_STAKE:.2f}, x2 after each loss, "
          f"reset on win, hypothetical ${RUIN_BANKROLL:.0f} bankroll cap for illustration)")


if __name__ == "__main__":
    asyncio.run(main())
