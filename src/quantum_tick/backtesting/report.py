from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from quantum_tick.backtesting.engine import SymbolBacktestResult
from quantum_tick.backtesting.metrics import SampleStats, compute_stats, max_streak, split_in_out_sample


@dataclass
class SymbolReport:
    symbol: str
    total_signals: int
    skip_counts: dict[str, int]
    in_sample: SampleStats | None
    out_of_sample: SampleStats | None
    max_consecutive_losses: int
    max_consecutive_wins: int


def build_report(
    results: dict[str, SymbolBacktestResult],
    in_sample_fraction: float = 0.7,
) -> list[SymbolReport]:
    reports = []
    for symbol, result in results.items():
        in_s, out_s = split_in_out_sample(result.outcomes, in_sample_fraction)
        reports.append(
            SymbolReport(
                symbol=symbol,
                total_signals=len(result.outcomes),
                skip_counts=result.skip_counts,
                in_sample=compute_stats(in_s),
                out_of_sample=compute_stats(out_s),
                max_consecutive_losses=max_streak(result.outcomes, "lost"),
                max_consecutive_wins=max_streak(result.outcomes, "won"),
            )
        )
    return reports


def format_report(reports: list[SymbolReport]) -> str:
    lines = []
    lines.append("=" * 100)
    lines.append(f"{'Symbol':<8} {'Split':<14} {'N':>6} {'Win%':>8} {'Breakeven%':>11} {'Edge':>8} {'z':>7} {'p-value':>9} {'Verdict':>12}")
    lines.append("-" * 100)

    for r in reports:
        for label, stats in (("in-sample", r.in_sample), ("out-of-sample", r.out_of_sample)):
            if stats is None:
                lines.append(f"{r.symbol:<8} {label:<14} {'(no trades)':>6}")
                continue
            verdict = "EDGE (sig.)" if stats.significant else ("worse" if stats.edge < 0 and stats.p_value < 0.05 else "no signal")
            lines.append(
                f"{r.symbol:<8} {label:<14} {stats.n:>6} "
                f"{stats.win_rate*100:>7.1f}% {stats.breakeven_rate*100:>10.1f}% "
                f"{stats.edge*100:>+7.1f}% {stats.z:>7.2f} {stats.p_value:>9.4f} {verdict:>12}"
            )
        lines.append(f"{r.symbol:<8} max consecutive losses: {r.max_consecutive_losses}   "
                     f"max consecutive wins: {r.max_consecutive_wins}")
        lines.append(f"{r.symbol:<8} skip_counts: {r.skip_counts}")
        lines.append("-" * 100)

    lines.append("=" * 100)
    return "\n".join(lines)


def save_report_json(reports: list[SymbolReport], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [
        {
            "symbol": r.symbol,
            "total_signals": r.total_signals,
            "skip_counts": r.skip_counts,
            "in_sample": asdict(r.in_sample) if r.in_sample else None,
            "out_of_sample": asdict(r.out_of_sample) if r.out_of_sample else None,
            "max_consecutive_losses": r.max_consecutive_losses,
            "max_consecutive_wins": r.max_consecutive_wins,
        }
        for r in reports
    ]
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
