"""Scan an ORSTAC-style Deriv Bot XML corpus, parse every Rise/Fall bot on
R_10-R_100, and report parse success/failure and candle- vs tick-based
split.

Usage: python scripts/xmlbots_scan_corpus.py [--corpus-dir PATH]
       (or set the XMLBOTS_CORPUS_DIR environment variable)

Expects a directory containing a `Bots_XML/` subfolder of Deriv Bot
(DBot/Blockly) XML exports -- see https://github.com/alanvito1/ORSTAC for
the corpus this was built against (not included in this repo).
"""

import argparse
import collections
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from quantum_tick.xmlbots.corpus import TARGET_SYMBOLS, find_candidate_files  # noqa: E402
from quantum_tick.xmlbots.interpreter import bot_requires_tick_data  # noqa: E402
from quantum_tick.xmlbots.parser import parse_file  # noqa: E402


def main(corpus_dir: Path) -> None:
    bots_xml_dir = corpus_dir / "Bots_XML"
    candidates = find_candidate_files(bots_xml_dir)
    print(f"Candidate files (contain 'risefall' + a target symbol as text): {len(candidates)}")

    supported = 0
    unsupported_reasons = collections.Counter()
    requires_ticks = 0
    candle_compatible = 0
    symbol_counts = collections.Counter()
    wrong_symbol_or_type = 0

    for fp in candidates:
        bot = parse_file(str(fp))
        if not bot.supported:
            unsupported_reasons[bot.unsupported_reason.split(":")[0]] += 1
            continue
        if bot.trade_type != "risefall" or bot.symbol not in TARGET_SYMBOLS:
            wrong_symbol_or_type += 1
            continue

        supported += 1
        symbol_counts[bot.symbol] += 1
        if bot_requires_tick_data(bot) or bot.duration_unit not in ("s", "m", "h"):
            requires_ticks += 1
        else:
            candle_compatible += 1

    print(f"\nSuccessfully parsed, Rise/Fall on R_10-R_100: {supported}")
    print(f"  -> candle-compatible (this backtest phase): {candle_compatible}")
    print(f"  -> requires tick data (future phase):        {requires_ticks}")
    print(f"Wrong symbol/trade_type after full parse (pre-filter was approximate): {wrong_symbol_or_type}")
    print(f"\nSymbol distribution (candle+tick combined): {dict(symbol_counts)}")

    print(f"\nUnsupported reasons (top 20 of {sum(unsupported_reasons.values())} unsupported):")
    for reason, count in unsupported_reasons.most_common(20):
        print(f"  {count:5d}  {reason}")


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
    main(args.corpus_dir)
