"""Run any registered strategy against cached real historical candles and
report in-sample / out-of-sample stats per symbol against the real
breakeven line. One engine, any strategy -- see
domain/strategies/base.py for what "pluggable" means here.

Usage:
    python scripts/run_backtest.py --strategy v8
    python scripts/run_backtest.py --strategy breakout
    python scripts/run_backtest.py --strategy random
    python scripts/run_backtest.py --strategy all      # side-by-side comparison

Run scripts/fetch_history.py first if the local cache is empty/thin.
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from quantum_tick.backtesting.engine import run_backtest  # noqa: E402
from quantum_tick.backtesting.payouts import build_payout_table  # noqa: E402
from quantum_tick.backtesting.report import build_report, format_report, save_report_json  # noqa: E402
from quantum_tick.config import get_settings  # noqa: E402
from quantum_tick.domain.strategies import STRATEGY_REGISTRY  # noqa: E402
from quantum_tick.infrastructure.deriv.auth import AccountBootstrap  # noqa: E402
from quantum_tick.infrastructure.deriv.client import DerivClient  # noqa: E402
from quantum_tick.logging_setup import setup_logging  # noqa: E402
from quantum_tick.persistence.db import make_session_factory  # noqa: E402
from quantum_tick.persistence.models import BacktestTrade  # noqa: E402
from quantum_tick.persistence.repository import BacktestRepository, CandleRepository  # noqa: E402

log = setup_logging("quantum_tick", "logs/run_backtest.log")

ALL_DURATIONS = list(range(1, 16))  # covers every strategy's duration range for payout quoting


async def run_one(strategy_name: str, candles_by_symbol: dict, payout_table, backtest_repo,
                   granularity: int, in_sample_fraction: float) -> None:
    strategy_cls = STRATEGY_REGISTRY[strategy_name]

    log.info(f"[{strategy_name}] replaying bar-by-bar (no lookahead)...")
    results = run_backtest(candles_by_symbol, strategy_cls, payout_table)

    reports = build_report(results, in_sample_fraction)
    print(f"\n### Strategy: {strategy_name} ###")
    print(format_report(reports))

    out_path = Path("reports") / f"backtest_report_{strategy_name}.json"
    save_report_json(reports, out_path)
    log.info(f"[{strategy_name}] saved JSON report to {out_path}")

    run_id = backtest_repo.create_run(
        symbols=list(candles_by_symbol.keys()),
        granularity=granularity,
        params={},
        notes=f"strategy={strategy_name}, no-lookahead bar replay",
    )
    trade_rows = []
    for symbol, result in results.items():
        cut = int(len(result.outcomes) * in_sample_fraction)
        for i, outcome in enumerate(result.outcomes):
            trade_rows.append(BacktestTrade(
                run_id=run_id,
                symbol=symbol,
                contract_type=outcome.contract_type,
                technique=outcome.technique,
                entry_open_time=outcome.entry_open_time,
                entry_price=outcome.entry_price,
                expiry_price=outcome.expiry_price,
                duration_mins=outcome.duration_mins,
                payout_ratio=outcome.payout_ratio,
                outcome=outcome.outcome,
                sample="in_sample" if i < cut else "out_of_sample",
            ))
    backtest_repo.add_trades(trade_rows)
    log.info(f"[{strategy_name}] persisted backtest run #{run_id} with {len(trade_rows)} trades")


async def main(strategy_arg: str, in_sample_fraction: float) -> None:
    settings = get_settings()
    granularity = settings.timeframe_seconds

    session_factory = make_session_factory(settings.database_url)
    candle_repo = CandleRepository(session_factory)
    backtest_repo = BacktestRepository(session_factory)

    candles_by_symbol = {}
    for symbol in settings.symbol_list:
        candles = candle_repo.load(symbol, granularity)
        candles_by_symbol[symbol] = candles
        log.info(f"[{symbol}] loaded {len(candles)} cached candles")
        if len(candles) < 200:
            log.warning(f"[{symbol}] very little cached history — run scripts/fetch_history.py first")

    log.info("Quoting live payout ratios for breakeven-line calculation...")
    bootstrap = AccountBootstrap(
        app_id=settings.deriv_app_id, api_token=settings.deriv_api_token,
        account_type=settings.deriv_account_type, currency=settings.deriv_currency,
    )
    ws_url = await bootstrap.get_websocket_url()
    async with DerivClient(ws_url) as client:
        payout_table = await build_payout_table(
            client, settings.symbol_list, durations=ALL_DURATIONS,
            currency=settings.deriv_currency, stake=settings.stake,
        )
    log.info(f"Quoted {len(payout_table)} (symbol, duration) payout ratios")

    strategy_names = list(STRATEGY_REGISTRY.keys()) if strategy_arg == "all" else [strategy_arg]
    for name in strategy_names:
        await run_one(name, candles_by_symbol, payout_table, backtest_repo, granularity, in_sample_fraction)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", choices=[*STRATEGY_REGISTRY.keys(), "all"], default="v8")
    parser.add_argument("--in-sample-fraction", type=float, default=0.7)
    args = parser.parse_args()
    asyncio.run(main(args.strategy, args.in_sample_fraction))
