"""End-to-end: load an ORSTAC-style Deriv Bot XML corpus, dedupe to
distinct strategies, backtest every one against every cached R_10-R_100
symbol through the same no-lookahead engine used for v8/breakout/random,
and report results with a Bonferroni correction sized to the actual number
of comparisons run (so a handful of "p<0.05" hits are expected by chance
alone and must not be mistaken for a real edge).

Usage: python scripts/xmlbots_backtest.py [--corpus-dir PATH]
       (or set the XMLBOTS_CORPUS_DIR environment variable)

Expects a directory containing a `Bots_XML/` subfolder of Deriv Bot
(DBot/Blockly) XML exports -- see https://github.com/alanvito1/ORSTAC for
the corpus this was built against (not included in this repo).

Requires: scripts/fetch_history.py already run (uses the cached candles,
no re-fetch) and a live connection only to quote payout ratios.
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from quantum_tick.backtesting.engine import run_backtest  # noqa: E402
from quantum_tick.backtesting.metrics import compute_stats, max_streak, split_in_out_sample  # noqa: E402
from quantum_tick.backtesting.payouts import build_payout_table  # noqa: E402
from quantum_tick.config import get_settings  # noqa: E402
from quantum_tick.domain.strategies.xmlbot_strategy import XmlBotStrategy  # noqa: E402
from quantum_tick.infrastructure.deriv.auth import AccountBootstrap  # noqa: E402
from quantum_tick.infrastructure.deriv.client import DerivClient  # noqa: E402
from quantum_tick.logging_setup import setup_logging  # noqa: E402
from quantum_tick.persistence.db import make_session_factory  # noqa: E402
from quantum_tick.persistence.repository import CandleRepository  # noqa: E402
from quantum_tick.xmlbots.corpus import dedupe_by_logic, load_candle_compatible_bots  # noqa: E402

log = setup_logging("quantum_tick", "logs/xmlbots_backtest.log")

IN_SAMPLE_FRACTION = 0.7


async def main(corpus_dir: Path) -> None:
    settings = get_settings()
    granularity = settings.timeframe_seconds

    log.info("Loading and parsing the ORSTAC corpus...")
    bots = load_candle_compatible_bots(corpus_dir)
    distinct = dedupe_by_logic(bots)
    log.info(f"{len(bots)} candle-compatible Rise/Fall bots on R_10-R_100 -> {len(distinct)} distinct strategies "
              f"after dedup")

    session_factory = make_session_factory(settings.database_url)
    candle_repo = CandleRepository(session_factory)
    candles_by_symbol = {s: candle_repo.load(s, granularity) for s in settings.symbol_list}
    for s, c in candles_by_symbol.items():
        log.info(f"[{s}] {len(c)} cached candles")

    durations_needed = sorted({
        max(1, round(d.representative.duration_value * {"s": 1 / 60, "m": 1, "h": 60}[d.representative.duration_unit]))
        for d in distinct
    })
    log.info(f"Quoting live payout ratios for durations: {durations_needed}")
    bootstrap = AccountBootstrap(
        app_id=settings.deriv_app_id, api_token=settings.deriv_api_token,
        account_type=settings.deriv_account_type, currency=settings.deriv_currency,
    )
    ws_url = await bootstrap.get_websocket_url()
    async with DerivClient(ws_url) as client:
        payout_table = await build_payout_table(
            client, settings.symbol_list, durations=durations_needed,
            currency=settings.deriv_currency, stake=settings.stake,
        )
    log.info(f"Quoted {len(payout_table)} (symbol, duration) payout ratios")

    log.info(f"Backtesting {len(distinct)} distinct strategies x {len(settings.symbol_list)} symbols "
              f"(no lookahead, real cached history)...")

    rows = []  # one row per (strategy, symbol)
    for i, strat in enumerate(distinct):
        bot = strat.representative
        results = run_backtest(candles_by_symbol, lambda bot=bot: XmlBotStrategy(bot), payout_table)
        for symbol, result in results.items():
            in_s, out_s = split_in_out_sample(result.outcomes, IN_SAMPLE_FRACTION)
            rows.append({
                "signature": strat.signature[:80],
                "duplicate_count": strat.duplicate_count,
                "representative_source": bot.source_path,
                "symbol": symbol,
                "in_sample": compute_stats(in_s),
                "out_of_sample": compute_stats(out_s),
                "max_consecutive_losses": max_streak(result.outcomes, "lost"),
            })
        if (i + 1) % 10 == 0:
            log.info(f"  ...{i + 1}/{len(distinct)} strategies backtested")

    # Bonferroni correction sized to the actual number of out-of-sample
    # comparisons that produced a testable result (n>0) -- not the raw
    # strategy count, since some (strategy, symbol) pairs never fire.
    out_of_sample_rows = [r for r in rows if r["out_of_sample"] is not None]
    n_tests = len(out_of_sample_rows)
    bonferroni_alpha = 0.05 / n_tests if n_tests > 0 else 0.05
    log.info(f"\n{n_tests} out-of-sample (strategy, symbol) comparisons with trades -> "
              f"Bonferroni-corrected threshold p < {bonferroni_alpha:.6f}")

    out_of_sample_rows.sort(key=lambda r: r["out_of_sample"].edge, reverse=True)

    print("\n" + "=" * 110)
    print(f"{'Source (representative)':<45} {'Sym':<6} {'N':>6} {'Win%':>7} {'BE%':>6} {'Edge':>7} "
          f"{'p-value':>10} {'Bonf.sig?':>10} {'Dups':>5}")
    print("-" * 110)
    for r in out_of_sample_rows[:30]:
        s = r["out_of_sample"]
        sig = "YES" if s.p_value < bonferroni_alpha and s.edge > 0 else ""
        name = Path(r["representative_source"]).name[:44]
        print(f"{name:<45} {r['symbol']:<6} {s.n:>6} {s.win_rate*100:>6.1f}% {s.breakeven_rate*100:>5.1f}% "
              f"{s.edge*100:>+6.1f}% {s.p_value:>10.6f} {sig:>10} {r['duplicate_count']:>5}")
    print("=" * 110)

    survivors = [r for r in out_of_sample_rows if r["out_of_sample"].p_value < bonferroni_alpha and r["out_of_sample"].edge > 0]
    print(f"\nSurvived Bonferroni correction with positive edge: {len(survivors)} / {n_tests}")
    for r in survivors:
        print(f"  {r['representative_source']}  [{r['symbol']}]  edge={r['out_of_sample'].edge*100:+.1f}%  "
              f"p={r['out_of_sample'].p_value:.6f}  n={r['out_of_sample'].n}")

    out_path = Path("reports") / "xmlbots_backtest.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    def stats_to_dict(s):
        return None if s is None else {
            "n": s.n, "wins": s.wins, "win_rate": s.win_rate, "breakeven_rate": s.breakeven_rate,
            "edge": s.edge, "z": s.z, "p_value": s.p_value, "total_pnl": s.total_pnl,
        }

    json_rows = [
        {**{k: v for k, v in r.items() if k not in ("in_sample", "out_of_sample")},
         "in_sample": stats_to_dict(r["in_sample"]), "out_of_sample": stats_to_dict(r["out_of_sample"])}
        for r in rows
    ]
    out_path.write_text(json.dumps({
        "n_distinct_strategies": len(distinct),
        "n_source_bots": len(bots),
        "bonferroni_alpha": bonferroni_alpha,
        "n_out_of_sample_comparisons": n_tests,
        "rows": json_rows,
    }, indent=2), encoding="utf-8")
    log.info(f"Saved full results to {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--corpus-dir", type=Path,
        default=Path(os.environ["XMLBOTS_CORPUS_DIR"]) if "XMLBOTS_CORPUS_DIR" in os.environ else None,
        help="Directory containing a Bots_XML/ subfolder of Deriv Bot XML exports. "
             "Falls back to the XMLBOTS_CORPUS_DIR environment variable.",
    )
    args = parser.parse_args()
    if args.corpus_dir is None:
        parser.error("pass --corpus-dir or set the XMLBOTS_CORPUS_DIR environment variable")
    asyncio.run(main(args.corpus_dir))
