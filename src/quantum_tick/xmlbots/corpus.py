"""Loads and filters the ORSTAC XML bot corpus into distinct, backtestable
strategies. Kept separate from parser.py (which only knows about one file
at a time)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from quantum_tick.xmlbots.interpreter import bot_requires_tick_data
from quantum_tick.xmlbots.ir import BotDefinition
from quantum_tick.xmlbots.parser import parse_file

TARGET_SYMBOLS = {"R_10", "R_25", "R_50", "R_75", "R_100"}


def find_candidate_files(bots_xml_dir: Path) -> list[Path]:
    """Cheap pre-filter (text search, not full XML parse) so the expensive
    parse only runs on files that stand a chance of matching."""
    candidates = []
    for dirpath, _, filenames in os.walk(bots_xml_dir):
        for name in filenames:
            if not name.lower().endswith(".xml"):
                continue
            fp = Path(dirpath) / name
            try:
                text = fp.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if "risefall" in text and any(s in text for s in TARGET_SYMBOLS):
                candidates.append(fp)
    return candidates


def load_candle_compatible_bots(corpus_dir: Path) -> list[BotDefinition]:
    """Every successfully-parsed Rise/Fall bot on a target symbol whose
    entry logic can be evaluated from candle-close data alone AND whose
    contract duration is time-based (s/m/h) rather than tick-based --
    excludes both a tick-based *indicator input* (bot_requires_tick_data)
    and a tick-based *contract duration* (a duration of N ticks resolves in
    a few seconds, faster than our 1-minute candle granularity can honestly
    score) -- see docs/research/xmlbots.md."""
    candidates = find_candidate_files(corpus_dir / "Bots_XML")
    bots = []
    for fp in candidates:
        bot = parse_file(str(fp))
        if not bot.supported:
            continue
        if bot.trade_type != "risefall" or bot.symbol not in TARGET_SYMBOLS:
            continue
        if bot.duration_unit not in ("s", "m", "h"):
            continue
        if bot_requires_tick_data(bot):
            continue
        bots.append(bot)
    return bots


@dataclass
class DistinctStrategy:
    signature: str
    representative: BotDefinition
    duplicate_count: int
    source_paths: list[str]


def dedupe_by_logic(bots: list[BotDefinition]) -> list[DistinctStrategy]:
    """Groups bots whose entry logic + duration are structurally identical
    (ignoring which symbol the original file happened to target, and which
    of the many near-duplicate filenames it came from) -- community bot
    collections are mostly a handful of real strategies copied under many
    names with cosmetic stake-size differences, not independent ideas.
    Each distinct strategy is then backtested against every target symbol
    regardless of which one its source file specified."""
    groups: dict[str, DistinctStrategy] = {}
    for bot in bots:
        signature = f"{bot.duration_unit}|{bot.duration_value}|{bot.entry_logic!r}"
        if signature in groups:
            groups[signature].duplicate_count += 1
            groups[signature].source_paths.append(bot.source_path)
        else:
            groups[signature] = DistinctStrategy(
                signature=signature, representative=bot, duplicate_count=1, source_paths=[bot.source_path],
            )
    return list(groups.values())
