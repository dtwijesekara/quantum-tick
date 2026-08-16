"""Backtest the Donchian breakout strategy (domain/breakout.py) against
cached real history. Parameters are fixed in this file's constants, chosen
before running -- do not tune them after seeing the result below; that
would be the same overfitting trap as sweeping v8's thresholds.

Usage: python scripts/run_backtest_breakout.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from quantum_tick.backtesting.breakout_engine import run_breakout_backtest  # noqa: E402
from quantum_tick.backtesting.metrics import compute_stats, max_streak, split_in_out_sample  # noqa: E402
from quantum_tick.backtesting.payouts import build_payout_table  # noqa: E402
from quantum_tick.config import get_settings  # noqa: E402
from quantum_tick.infrastructure.deriv.auth import AccountBootstrap  # noqa: E402
from quantum_tick.infrastructure.deriv.client import DerivClient  # noqa: E402
from quantum_tick.persistence.db import make_session_factory  # noqa: E402
from quantum_tick.persistence.repository import CandleRepository  # noqa: E402

CHANNEL_LOOKBACK = 20  # Turtle-Trading-canonical Donchian window, not fit to this data
DURATION_MINS = 3


async def main() -> None:
    settings = get_settings()
    granularity = settings.timeframe_seconds

    session_factory = make_session_factory(settings.database_url)
    candle_repo = CandleRepository(session_factory)

    bootstrap = AccountBootstrap(
        app_id=settings.deriv_app_id,
        api_token=settings.deriv_api_token,
        account_type=settings.deriv_account_type,
        currency=settings.deriv_currency,
    )
    ws_url = await bootstrap.get_websocket_url()
    async with DerivClient(ws_url) as client:
        payout_table = await build_payout_table(
            client, settings.symbol_list, durations=[DURATION_MINS],
            currency=settings.deriv_currency, stake=settings.stake,
        )

    print(f"Donchian breakout: channel_lookback={CHANNEL_LOOKBACK}, duration={DURATION_MINS}min")
    print("=" * 100)
    print(f"{'Symbol':<8} {'Split':<14} {'N':>6} {'Win%':>8} {'Breakeven%':>11} {'Edge':>8} {'z':>7} {'p-value':>9} {'Verdict':>12}")
    print("-" * 100)

    for symbol in settings.symbol_list:
        candles = candle_repo.load(symbol, granularity)
        result = run_breakout_backtest(symbol, candles, CHANNEL_LOOKBACK, DURATION_MINS, payout_table)

        in_s, out_s = split_in_out_sample(result.outcomes, 0.7)
        for label, subset in (("in-sample", in_s), ("out-of-sample", out_s)):
            stats = compute_stats(subset)
            if stats is None:
                print(f"{symbol:<8} {label:<14} (no trades)")
                continue
            verdict = "EDGE (sig.)" if stats.significant else ("worse" if stats.edge < 0 and stats.p_value < 0.05 else "no signal")
            print(f"{symbol:<8} {label:<14} {stats.n:>6} {stats.win_rate*100:>7.1f}% "
                  f"{stats.breakeven_rate*100:>10.1f}% {stats.edge*100:>+7.1f}% {stats.z:>7.2f} "
                  f"{stats.p_value:>9.4f} {verdict:>12}")
        print(f"{symbol:<8} total_signals={len(result.outcomes)}  "
              f"max_consecutive_losses={max_streak(result.outcomes, 'lost')}  "
              f"max_consecutive_wins={max_streak(result.outcomes, 'won')}")
        print("-" * 100)


if __name__ == "__main__":
    asyncio.run(main())
