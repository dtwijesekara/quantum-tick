"""Pure domain value objects -- no I/O, no framework dependencies."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class StrategyParams:
    """All tunable thresholds for the v8 signal engine (see dt_bot_v8.py).

    Kept as an explicit, constructible dataclass (rather than module globals)
    so the backtester can run the exact same logic under different parameter
    sets without mutating shared state -- see
    docs/postmortem/PROJECT_POSTMORTEM.md items 15 and 19.
    """

    trend_min_candles: int = 3
    trend_max_candles: int = 5
    bos_lookback: int = 15
    swing_lookback: int = 20
    swing_strength: int = 2
    avg_body_lookback: int = 5
    min_duration_mins: int = 1
    max_duration_mins: int = 15
    large_fvg_body_mult: float = 2.0

    hop_min_body_mult: float = 0.10
    engulf_coverage: float = 0.70

    post_impulse_mult: float = 2.5
    late_entry_mult: float = 1.5

    chop_lookback: int = 8
    chop_alter_threshold: float = 0.60
    chop_body_threshold: float = 0.70
    chop_dir_threshold: float = 0.62

    def min_candles_needed(self) -> int:
        return self.bos_lookback + self.swing_lookback + self.swing_strength + self.chop_lookback + 8


@dataclass(frozen=True)
class Signal:
    symbol: str
    contract_type: str  # "CALL" or "PUT"
    trend: str
    structure: str
    entries: list[str]
    target: float
    distance: float
    avg_body: float
    duration_mins: int
    price: float
    signal_open_time: int
    skip_reasons: dict = field(default_factory=dict)


@dataclass(frozen=True)
class SkipResult:
    reason: str
    detail: str = ""
