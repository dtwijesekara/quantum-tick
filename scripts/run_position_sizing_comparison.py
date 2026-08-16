"""Flat-stake vs martingale, simulated over a real strategy's trade sequence.
Martingale can't fix a lack of edge (it doesn't touch win probability);
this quantifies what it actually costs in real observed streaks instead of
asserting it.

Usage: python scripts/run_position_sizing_comparison.py [--strategy breakout]
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from quantum_tick.backtesting.engine import run_symbol_backtest  # noqa: E402
from quantum_tick.backtesting.payouts import build_payout_table  # noqa: E402
from quantum_tick.backtesting.position_sizing import simulate_flat_stake, simulate_martingale  # noqa: E402
from quantum_tick.config import get_settings  # noqa: E402
from quantum_tick.domain.strategies import STRATEGY_REGISTRY  # noqa: E402
from quantum_tick.infrastructure.deriv.auth import AccountBootstrap  # noqa: E402
from quantum_tick.infrastructure.deriv.client import DerivClient  # noqa: E402
from quantum_tick.persistence.db import make_session_factory  # noqa: E402
from quantum_tick.persistence.repository import CandleRepository  # noqa: E402

BASE_STAKE = 1.0
RUIN_BANKROLL = 1000.0  # a generously large hypothetical account, for illustration


async def main(strategy_name: str) -> None:
    settings = get_settings()
    granularity = settings.timeframe_seconds
    candle_repo = CandleRepository(make_session_factory(settings.database_url))
    strategy_cls = STRATEGY_REGISTRY[strategy_name]

    bootstrap = AccountBootstrap(
        app_id=settings.deriv_app_id, api_token=settings.deriv_api_token,
        account_type=settings.deriv_account_type, currency=settings.deriv_currency,
    )
    ws_url = await bootstrap.get_websocket_url()
    async with DerivClient(ws_url) as client:
        payout_table = await build_payout_table(
            client, settings.symbol_list, durations=list(range(1, 16)),
            currency=settings.deriv_currency, stake=BASE_STAKE,
        )

    print(f"Strategy: {strategy_name}")
    print(f"{'Symbol':<8} {'N':>6} {'Flat PnL':>10} {'Flat MaxDD':>11} "
          f"{'Mart. PnL':>10} {'Mart. MaxDD':>12} {'Peak stake':>12} {'Ruined?':>10}")
    print("-" * 90)

    for symbol in settings.symbol_list:
        candles = candle_repo.load(symbol, granularity)
        result = run_symbol_backtest(symbol, candles, strategy_cls(), payout_table)
        outcomes = result.outcomes

        flat = simulate_flat_stake(outcomes, stake=BASE_STAKE)
        mart = simulate_martingale(outcomes, base_stake=BASE_STAKE, multiplier=2.0, ruin_bankroll=RUIN_BANKROLL)

        ruined = f"YES @ trade {mart.ruin_index}" if mart.ruin_index is not None else "no"
        print(f"{symbol:<8} {len(outcomes):>6} {flat.final_pnl:>+10.2f} {flat.max_drawdown:>11.2f} "
              f"{mart.final_pnl:>+10.2f} {mart.max_drawdown:>12.2f} {mart.peak_stake_required:>12.2f} {ruined:>10}")

    print(f"\n(martingale simulated with base stake ${BASE_STAKE:.2f}, x2 after each loss, "
          f"reset on win, hypothetical ${RUIN_BANKROLL:.0f} bankroll cap for illustration)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", choices=list(STRATEGY_REGISTRY.keys()), default="breakout")
    args = parser.parse_args()
    asyncio.run(main(args.strategy))
